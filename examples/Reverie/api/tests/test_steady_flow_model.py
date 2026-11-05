"""Compile and exercise the receive statistics without an ns-3 installation."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


MODEL = Path(__file__).resolve().parents[4] / 'src/point-to-point/model'

DRIVER = r'''
#include "steady-flow-model.h"
#include <cassert>
#include <iostream>
#include <string>

using namespace flow_acc;

static bool close(long double a, long double b) { return std::fabs(a-b) < 1e-10L; }

static void warm(SamplingState& state, const SamplingPolicy& policy, uint64_t cadence = 100,
                 uint32_t payload = 100, uint32_t wire = 120, uint64_t offset = 0) {
    const uint64_t end = policy.period_ns * policy.window_samples;
    for (uint64_t t = 0; t <= end; t += cadence) ObservePacket(state, t+offset, payload, wire, policy);
}

static Sample sample(uint64_t bytes, uint64_t duration) {
    Sample result;
    result.payload_bytes = bytes;
    result.wire_bytes = bytes + 40;
    result.elapsed_ns = duration;
    result.packet_count = 10;
    result.valid_for_steady = true;
    return result;
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string name = argv[1];
    if (name == "first_packet_and_elapsed") {
        SamplingPolicy policy(1000, 3);
        SamplingState state;
        auto first = ObservePacket(state, 100, 100, 140, policy);
        assert(!first.sampled && state.payload_bytes == 100 && state.wire_bytes == 140);
        ObservePacket(state, 500, 100, 140, policy);
        auto result = ObservePacket(state, 1400, 100, 140, policy);
        assert(result.sampled && result.sample.payload_bytes == 200);
        assert(result.sample.wire_bytes == 280 && result.sample.elapsed_ns == 1300);
        assert(result.sample.packet_count == 2 && close(result.sample.payload_gbps, 1600.0L/1300));
        assert(state.payload_bytes == 100 && state.wire_bytes == 140 && state.packet_count == 1);
        assert(state.latest_payload_bytes == 200 && state.latest_elapsed_ns == 1300);
    } else if (name == "ten_complete_samples") {
        SamplingPolicy policy(1000, 10);
        SamplingState state;
        for (uint64_t t=0; t<=9000; t+=100) ObservePacket(state,t,100,120,policy);
        assert(state.samples.size() == 9 && !state.steady);
        for (uint64_t t=9100; t<=10000; t+=100) ObservePacket(state,t,100,120,policy);
        assert(state.samples.size() == 10 && IsFreshSteady(state,10000,policy));
        for (uint64_t t=10100; t<=20000; t+=100) ObservePacket(state,t,100,120,policy);
        assert(state.samples.size() == 10 && IsFreshSteady(state,20000,policy));
        auto rate = GetPayloadRate(state);
        assert(rate.valid && rate.payload_bytes == 10000 && rate.elapsed_ns == 10000);
        assert(close(rate.BytesPerNs(),1));
    } else if (name == "period_overshoot") {
        SamplingPolicy policy(1000,3);
        SamplingState state;
        uint64_t sampled_payload = 0;
        for (uint64_t index=0; index<=12; ++index) {
            auto result = ObservePacket(state,index*333,1000,1058,policy);
            if (result.sampled) {
                assert(result.sample.elapsed_ns == 1332 && result.sample.payload_bytes == 4000);
                assert(close(result.sample.payload_gbps,32000.0L/1332));
                sampled_payload += result.sample.payload_bytes;
            }
        }
        assert(sampled_payload + state.payload_bytes == 13000);
        assert(IsFreshSteady(state,3996,policy));
    } else if (name == "no_percentage_tolerance") {
        SamplingPolicy policy(10000,3,1);
        std::vector<Sample> values{sample(30000,10000),sample(30000,10001),sample(30000,10000)};
        assert(WindowIsSteady(values,policy));
        values[1] = sample(30000,10003);
        assert(!WindowIsSteady(values,policy));
        values[1] = sample(31500,10000); // A 5% rate change is never timing quantization.
        assert(!WindowIsSteady(values,policy));
        values[1] = sample(30000,10001);
        assert(!WindowIsSteady(values,SamplingPolicy(10000,3,0)));
    } else if (name == "stale_and_restart") {
        SamplingPolicy policy(1000,3);
        SamplingState state;
        warm(state,policy);
        assert(IsFreshSteady(state,3000,policy));
        assert(!IsFreshSteady(state,4001,policy));
        assert(InvalidateIfStale(state,4001,policy));
        assert(!state.steady && state.samples.empty() && !GetPayloadRate(state).valid);
        assert(state.payload_bytes == 100); // No invented traffic and no lost counter.
        auto result = ObservePacket(state,5000,100,120,policy);
        assert(result.sampled && !result.sample.valid_for_steady && result.sample.payload_bytes == 100);
        assert(state.samples.empty() && state.payload_bytes == 100);
        for (uint64_t t=5100; t<=8000; t+=100) ObservePacket(state,t,100,120,policy);
        assert(IsFreshSteady(state,8000,policy));
    } else if (name == "changed_rate_and_stage") {
        SamplingPolicy policy(1000,3);
        SamplingState state;
        warm(state,policy);
        for (uint64_t t=3200; t<=4000; t+=200) ObservePacket(state,t,100,120,policy);
        assert(!state.steady); // First slower sample invalidates the old window.
        for (uint64_t t=4200; t<=6000; t+=200) ObservePacket(state,t,100,120,policy);
        assert(IsFreshSteady(state,6000,policy));
        assert(close(GetPayloadBytesPerNs(state),0.5));
        SamplingState new_stage;
        ObservePacket(new_stage,6000,100,120,policy);
        assert(!IsFreshSteady(new_stage,6000,policy));
        assert(!(IsFreshSteady(state,6000,policy) && IsFreshSteady(new_stage,6000,policy)));
    } else if (name == "unequal_independent_flows") {
        SamplingPolicy policy(1000,3);
        SamplingState fast,slow;
        warm(fast,policy,100,100,120,0);
        warm(slow,policy,200,100,120,50);
        assert(IsFreshSteady(fast,3100,policy) && IsFreshSteady(slow,3100,policy));
        assert(close(GetPayloadBytesPerNs(fast),1) && close(GetPayloadBytesPerNs(slow),0.5));
        InvalidateIfStale(slow,4100,policy);
        assert(!slow.steady && fast.steady);
    } else if (name == "payload_not_frame") {
        SamplingPolicy policy(1000,3);
        SamplingState a,b,control;
        warm(a,policy,100,100,158);
        warm(b,policy,100,100,100);
        warm(control,policy,100,0,64);
        assert(a.steady && b.steady && !control.steady);
        assert(close(GetPayloadBytesPerNs(a),GetPayloadBytesPerNs(b)));
        assert(a.samples.back().wire_bytes == 1580 && b.samples.back().wire_bytes == 1000);
        assert(!GetPayloadRate(control).valid);
    } else if (name == "weighted_rate_and_overflow") {
        SamplingState state;
        state.samples = {sample(1000,1000),sample(3000,2000)};
        const auto rate = GetPayloadRate(state);
        assert(rate.valid && rate.payload_bytes == 4000 && rate.elapsed_ns == 3000);
        assert(close(rate.BytesPerNs(),4.0L/3));
        state.samples = {sample(std::numeric_limits<uint64_t>::max(),1000),sample(1,1000)};
        assert(!GetPayloadRate(state).valid);
    } else if (name == "wide_bytes_and_same_time") {
        SamplingPolicy policy(1000,3);
        SamplingState state;
        ObservePacket(state,0,70000,72000,policy);
        ObservePacket(state,0,1,64,policy);
        assert(state.payload_bytes == 70001 && state.wire_bytes == 72064);
        auto result = ObservePacket(state,1000,100,120,policy);
        assert(result.sampled && result.sample.payload_bytes == 70001 && result.sample.elapsed_ns == 1000);
    } else if (name == "time_rollback_and_bad_input") {
        SamplingPolicy policy(1000,3);
        SamplingState state;
        warm(state,policy);
        auto result = ObservePacket(state,2999,100,120,policy);
        assert(result.history_reset && !result.sampled && !state.steady);
        assert(state.interval_start_ns == 2999 && state.payload_bytes == 100);
        bool rejected = false;
        try { ObservePacket(state,3000,200,100,policy); }
        catch (const std::invalid_argument&) { rejected = true; }
        assert(rejected);
        rejected = false;
        try { ObservePacket(state,3000,100,120,SamplingPolicy(0,3)); }
        catch (const std::invalid_argument&) { rejected = true; }
        assert(rejected);
    } else {
        return 2;
    }
    std::cout << "ok " << name << std::endl;
}
'''


@pytest.fixture(scope='session')
def steady_model_binary(tmp_path_factory):
    compiler = os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        pytest.skip('A host C++ compiler is required for steady-flow-model tests')
    directory = tmp_path_factory.mktemp('steady-flow-model')
    source = directory / 'test_model.cc'
    binary = directory / ('test_model.exe' if os.name == 'nt' else 'test_model')
    source.write_text(DRIVER,encoding='utf-8')
    command = [compiler,'-std=c++17','-Wall','-Wextra','-pedantic','-Werror',
               '-I',str(MODEL),str(source),'-o',str(binary)]
    if os.name == 'nt':
        command += ['-static-libgcc','-static-libstdc++']
    compiled = subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return binary


@pytest.mark.parametrize('case',[
    'first_packet_and_elapsed','ten_complete_samples','period_overshoot','no_percentage_tolerance',
    'stale_and_restart','changed_rate_and_stage','unequal_independent_flows','payload_not_frame',
    'weighted_rate_and_overflow','wide_bytes_and_same_time','time_rollback_and_bad_input',
])
def test_steady_flow_statistics(steady_model_binary,case):
    result = subprocess.run([str(steady_model_binary),case],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'ok '+case
