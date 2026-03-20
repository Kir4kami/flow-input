/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
#ifndef SWITCH_TIMING_TAG_H
#define SWITCH_TIMING_TAG_H

#include "ns3/tag.h"

namespace ns3 {

class SwitchTimingTag : public Tag
{
public:
  SwitchTimingTag ();

  static TypeId GetTypeId (void);
  virtual TypeId GetInstanceTypeId (void) const;
  virtual uint32_t GetSerializedSize (void) const;
  virtual void Serialize (TagBuffer i) const;
  virtual void Deserialize (TagBuffer i);
  virtual void Print (std::ostream &os) const;

  void SetIngressTimeNs (uint64_t t);
  uint64_t GetIngressTimeNs () const;

  void SetEgressTimeNs (uint64_t t);
  uint64_t GetEgressTimeNs () const;

  void SetIngressWallTimeNs (uint64_t t);
  uint64_t GetIngressWallTimeNs () const;

  void SetEgressWallTimeNs (uint64_t t);
  uint64_t GetEgressWallTimeNs () const;

  void SetSwitchId (uint32_t id);
  uint32_t GetSwitchId () const;

  void SetInDev (uint32_t dev);
  uint32_t GetInDev () const;

  void SetOutDev (uint32_t dev);
  uint32_t GetOutDev () const;

  void SetQIndex (uint32_t q);
  uint32_t GetQIndex () const;

private:
  uint64_t m_ingressTimeNs;
  uint64_t m_egressTimeNs;
  uint64_t m_ingressWallTimeNs;
  uint64_t m_egressWallTimeNs;
  uint32_t m_switchId;
  uint32_t m_inDev;
  uint32_t m_outDev;
  uint32_t m_qIndex;
};

} // namespace ns3

#endif /* SWITCH_TIMING_TAG_H */
