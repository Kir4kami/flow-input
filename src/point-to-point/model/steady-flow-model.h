#ifndef STEADY_FLOW_MODEL_H
#define STEADY_FLOW_MODEL_H

// Pure receive-side statistics. This header neither schedules packets nor
// changes sender/receiver sequence numbers or acknowledgements.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

namespace flow_acc {

struct SamplingPolicy {
    uint64_t period_ns;
    std::size_t window_samples;
    uint64_t clock_quantum_ns;
    uint64_t stale_after_ns;

    explicit SamplingPolicy(uint64_t period = 10000, std::size_t window = 10,
                            uint64_t quantum = 1, uint64_t stale = 0)
        : period_ns(period), window_samples(window), clock_quantum_ns(quantum),
          stale_after_ns(stale) {}
};

struct Sample {
    uint64_t payload_bytes = 0;
    uint64_t wire_bytes = 0;
    uint64_t elapsed_ns = 0;
    uint64_t packet_count = 0;
    double payload_gbps = 0;
    bool valid_for_steady = false;
};

struct SamplingState {
    bool initialized = false;
    uint64_t interval_start_ns = 0;
    uint64_t last_packet_ns = 0;
    uint64_t payload_bytes = 0;
    uint64_t wire_bytes = 0;
    uint64_t packet_count = 0;
    bool interval_invalidated = false;
    std::vector<Sample> samples;
    bool steady = false;
    uint64_t latest_payload_bytes = 0;
    uint64_t latest_elapsed_ns = 0;
};

struct SampleResult {
    bool sampled = false;
    bool history_reset = false;
    Sample sample;
};

struct PayloadRate {
    uint64_t payload_bytes = 0;
    uint64_t elapsed_ns = 0;
    bool valid = false;

    long double BytesPerNs() const {
        return valid && elapsed_ns ? static_cast<long double>(payload_bytes) / elapsed_ns : 0;
    }
};

inline void ValidatePolicy(const SamplingPolicy& policy) {
    if (!policy.period_ns || policy.window_samples < 2 || policy.clock_quantum_ns >= policy.period_ns) {
        throw std::invalid_argument("Invalid steady-flow sampling policy");
    }
}

inline uint64_t FreshnessLimit(const SamplingPolicy& policy) {
    return policy.stale_after_ns ? policy.stale_after_ns : policy.period_ns;
}

inline void ClearHistory(SamplingState& state) {
    state.samples.clear();
    state.steady = false;
    state.interval_invalidated = true;
}

inline bool InvalidateIfStale(SamplingState& state, uint64_t now_ns,
                              const SamplingPolicy& policy = SamplingPolicy()) {
    ValidatePolicy(policy);
    if (!state.initialized) return false;
    if (now_ns < state.last_packet_ns || now_ns - state.last_packet_ns > FreshnessLimit(policy)) {
        ClearHistory(state);
        return true;
    }
    return false;
}

inline bool WindowIsSteady(const std::vector<Sample>& samples, const SamplingPolicy& policy) {
    ValidatePolicy(policy);
    if (samples.size() != policy.window_samples) return false;
    long double lower = 0;
    long double upper = std::numeric_limits<long double>::infinity();
    for (const Sample& sample : samples) {
        if (!sample.valid_for_steady || !sample.payload_bytes || sample.elapsed_ns < policy.period_ns ||
            sample.elapsed_ns <= policy.clock_quantum_ns) return false;
        // Arrival timestamps have integer-nanosecond resolution. The entire
        // window must admit ONE common rate within that one-tick endpoint
        // quantization, rather than a tunable relative-percentage tolerance.
        const long double duration = sample.elapsed_ns;
        const long double quantum = policy.clock_quantum_ns;
        lower = std::max(lower, static_cast<long double>(sample.payload_bytes) / (duration + quantum));
        upper = std::min(upper, static_cast<long double>(sample.payload_bytes) / (duration - quantum));
    }
    const long double roundoff = 16 * std::numeric_limits<long double>::epsilon() * std::max(lower, upper);
    return lower > 0 && lower <= upper + roundoff;
}

inline bool IsFreshSteady(const SamplingState& state, uint64_t now_ns,
                           const SamplingPolicy& policy = SamplingPolicy()) {
    ValidatePolicy(policy);
    return state.initialized && state.steady && !state.interval_invalidated &&
           state.samples.size() == policy.window_samples && now_ns >= state.last_packet_ns &&
           now_ns - state.last_packet_ns <= FreshnessLimit(policy);
}

inline PayloadRate GetPayloadRate(const SamplingState& state) {
    PayloadRate result;
    if (state.samples.empty() || state.interval_invalidated) return result;
    for (const Sample& sample : state.samples) {
        if (!sample.valid_for_steady || !sample.elapsed_ns ||
            sample.payload_bytes > std::numeric_limits<uint64_t>::max() - result.payload_bytes ||
            sample.elapsed_ns > std::numeric_limits<uint64_t>::max() - result.elapsed_ns) return PayloadRate();
        result.payload_bytes += sample.payload_bytes;
        result.elapsed_ns += sample.elapsed_ns;
    }
    result.valid = result.payload_bytes > 0 && result.elapsed_ns > 0;
    return result;
}

inline long double GetPayloadBytesPerNs(const SamplingState& state) {
    return GetPayloadRate(state).BytesPerNs();
}

inline SampleResult ObservePacket(SamplingState& state, uint64_t now_ns,
                                  uint32_t payload_bytes, uint32_t wire_bytes,
                                  const SamplingPolicy& policy = SamplingPolicy()) {
    ValidatePolicy(policy);
    if (wire_bytes < payload_bytes) throw std::invalid_argument("Wire bytes cannot be less than payload bytes");
    SampleResult result;
    if (state.initialized && now_ns < state.last_packet_ns) {
        // A time rollback cannot be interpreted as an elapsed receive interval.
        state = SamplingState();
        result.history_reset = true;
    }
    if (!state.initialized) {
        state.initialized = true;
        state.interval_start_ns = now_ns;
    } else {
        result.history_reset = InvalidateIfStale(state, now_ns, policy);
        const uint64_t elapsed = now_ns - state.interval_start_ns;
        if (elapsed >= policy.period_ns) {
            result.sampled = true;
            Sample& sample = result.sample;
            sample.payload_bytes = state.payload_bytes;
            sample.wire_bytes = state.wire_bytes;
            sample.elapsed_ns = elapsed;
            sample.packet_count = state.packet_count;
            sample.payload_gbps = static_cast<double>(static_cast<long double>(sample.payload_bytes) * 8 / elapsed);
            sample.valid_for_steady = sample.payload_bytes > 0 && sample.packet_count > 0 &&
                                      !state.interval_invalidated;
            state.latest_payload_bytes = sample.payload_bytes;
            state.latest_elapsed_ns = sample.elapsed_ns;
            if (sample.valid_for_steady) {
                state.samples.push_back(sample);
                if (state.samples.size() > policy.window_samples) state.samples.erase(state.samples.begin());
                state.steady = WindowIsSteady(state.samples, policy);
            } else {
                ClearHistory(state);
                result.history_reset = true;
            }
            state.payload_bytes = 0;
            state.wire_bytes = 0;
            state.packet_count = 0;
            state.interval_start_ns = now_ns;
            state.interval_invalidated = false;
        }
    }
    // [start, now) was sampled above. This arrival belongs only to the next
    // interval, including the first arrival; callers must not pre-count it.
    if (state.payload_bytes > std::numeric_limits<uint64_t>::max() - payload_bytes ||
        state.wire_bytes > std::numeric_limits<uint64_t>::max() - wire_bytes ||
        state.packet_count == std::numeric_limits<uint64_t>::max()) {
        throw std::overflow_error("Receive statistics counter overflow");
    }
    state.payload_bytes += payload_bytes;
    state.wire_bytes += wire_bytes;
    ++state.packet_count;
    state.last_packet_ns = now_ns;
    if (!payload_bytes) {
        ClearHistory(state);
        result.history_reset = true;
    }
    return result;
}

} // namespace flow_acc

#endif
