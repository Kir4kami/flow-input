/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
#include "switch-timing-tag.h"

#include "ns3/log.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE ("SwitchTimingTag");
NS_OBJECT_ENSURE_REGISTERED (SwitchTimingTag);

SwitchTimingTag::SwitchTimingTag ()
  : m_ingressTimeNs (0),
    m_egressTimeNs (0),
    m_ingressWallTimeNs (0),
    m_egressWallTimeNs (0),
    m_switchId (0),
    m_inDev (0),
    m_outDev (0),
    m_qIndex (0)
{
}

TypeId
SwitchTimingTag::GetTypeId (void)
{
  static TypeId tid = TypeId ("ns3::SwitchTimingTag")
    .SetParent<Tag> ()
    .SetGroupName ("PointToPoint")
    .AddConstructor<SwitchTimingTag> ();
  return tid;
}

TypeId
SwitchTimingTag::GetInstanceTypeId (void) const
{
  return GetTypeId ();
}

uint32_t
SwitchTimingTag::GetSerializedSize (void) const
{
  return 4 * sizeof(uint64_t) + 4 * sizeof(uint32_t);
}

void
SwitchTimingTag::Serialize (TagBuffer i) const
{
  i.WriteU64 (m_ingressTimeNs);
  i.WriteU64 (m_egressTimeNs);
  i.WriteU64 (m_ingressWallTimeNs);
  i.WriteU64 (m_egressWallTimeNs);
  i.WriteU32 (m_switchId);
  i.WriteU32 (m_inDev);
  i.WriteU32 (m_outDev);
  i.WriteU32 (m_qIndex);
}

void
SwitchTimingTag::Deserialize (TagBuffer i)
{
  m_ingressTimeNs = i.ReadU64 ();
  m_egressTimeNs = i.ReadU64 ();
  m_ingressWallTimeNs = i.ReadU64 ();
  m_egressWallTimeNs = i.ReadU64 ();
  m_switchId = i.ReadU32 ();
  m_inDev = i.ReadU32 ();
  m_outDev = i.ReadU32 ();
  m_qIndex = i.ReadU32 ();
}

void
SwitchTimingTag::Print (std::ostream &os) const
{
  os << "switch=" << m_switchId
     << ", inDev=" << m_inDev
     << ", outDev=" << m_outDev
     << ", qIndex=" << m_qIndex
     << ", ingressNs=" << m_ingressTimeNs
     << ", egressNs=" << m_egressTimeNs;
}

void
SwitchTimingTag::SetIngressTimeNs (uint64_t t)
{
  m_ingressTimeNs = t;
}

uint64_t
SwitchTimingTag::GetIngressTimeNs () const
{
  return m_ingressTimeNs;
}

void
SwitchTimingTag::SetEgressTimeNs (uint64_t t)
{
  m_egressTimeNs = t;
}

uint64_t
SwitchTimingTag::GetEgressTimeNs () const
{
  return m_egressTimeNs;
}

void
SwitchTimingTag::SetIngressWallTimeNs (uint64_t t)
{
  m_ingressWallTimeNs = t;
}

uint64_t
SwitchTimingTag::GetIngressWallTimeNs () const
{
  return m_ingressWallTimeNs;
}

void
SwitchTimingTag::SetEgressWallTimeNs (uint64_t t)
{
  m_egressWallTimeNs = t;
}

uint64_t
SwitchTimingTag::GetEgressWallTimeNs () const
{
  return m_egressWallTimeNs;
}

void
SwitchTimingTag::SetSwitchId (uint32_t id)
{
  m_switchId = id;
}

uint32_t
SwitchTimingTag::GetSwitchId () const
{
  return m_switchId;
}

void
SwitchTimingTag::SetInDev (uint32_t dev)
{
  m_inDev = dev;
}

uint32_t
SwitchTimingTag::GetInDev () const
{
  return m_inDev;
}

void
SwitchTimingTag::SetOutDev (uint32_t dev)
{
  m_outDev = dev;
}

uint32_t
SwitchTimingTag::GetOutDev () const
{
  return m_outDev;
}

void
SwitchTimingTag::SetQIndex (uint32_t q)
{
  m_qIndex = q;
}

uint32_t
SwitchTimingTag::GetQIndex () const
{
  return m_qIndex;
}

} // namespace ns3
