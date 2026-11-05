/*
 * Copyright (c) 2005,2006 INRIA
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 * Author: Mathieu Lacage <mathieu.lacage@sophia.inria.fr>
 */
#include "ns3/calendar-scheduler.h"
#include "ns3/default-simulator-impl.h"
#include "ns3/heap-scheduler.h"
#include "ns3/list-scheduler.h"
#include "ns3/map-scheduler.h"
#include "ns3/mixed-granularity.h"
#include "ns3/priority-queue-scheduler.h"
#include "ns3/simulator.h"
#include "ns3/test.h"

#include <thread>
#include <vector>

using namespace ns3;

/**
 * \file
 * \ingroup simulator-tests
 * Simulator class test suite
 */

/**
 * \ingroup core-tests
 * \defgroup simulator-tests Simulator class tests
 */

/**
 * \ingroup simulator-tests
 *
 * \brief Check that basic event handling is working with different Simulator implementations.
 */
class SimulatorEventsTestCase : public TestCase
{
  public:
    /**
     * Constructor.
     * \param schedulerFactory Scheduler factory.
     */
    SimulatorEventsTestCase(ObjectFactory schedulerFactory);
    void DoRun() override;
    /**
     * Test Event.
     * \param value Event parameter.
     * @{
     */
    void EventA(int value);
    void EventB(int value);
    void EventC(int value);
    void EventD(int value);
    /** @} */

    /**
     * Test Event.
     */
    void Eventfoo0();

    /**
     * Get the simulator time.
     * \return The actual time [ms].
     */
    uint64_t NowUs();
    /**
     * Checks that the events has been destroyed.
     */
    void Destroy();
    /**
     * Checks that events are properly handled.
     * @{
     */
    bool m_a;
    bool m_b;
    bool m_c;
    bool m_d;
    bool m_destroy;
    /** @} */

    EventId m_idC;                    //!< Event C.
    EventId m_destroyId;              //!< Event to check event lifetime.
    ObjectFactory m_schedulerFactory; //!< Scheduler factory.
};

SimulatorEventsTestCase::SimulatorEventsTestCase(ObjectFactory schedulerFactory)
    : TestCase("Check that basic event handling is working with " +
               schedulerFactory.GetTypeId().GetName()),
      m_schedulerFactory(schedulerFactory)
{
}

uint64_t
SimulatorEventsTestCase::NowUs()
{
    uint64_t ns = Now().GetNanoSeconds();
    return ns / 1000;
}

void
SimulatorEventsTestCase::EventA(int /* a */)
{
    m_a = false;
}

void
SimulatorEventsTestCase::EventB(int b)
{
    m_b = !(b != 2 || NowUs() != 11);
    Simulator::Remove(m_idC);
    Simulator::Schedule(MicroSeconds(10), &SimulatorEventsTestCase::EventD, this, 4);
}

void
SimulatorEventsTestCase::EventC(int /* c */)
{
    m_c = false;
}

void
SimulatorEventsTestCase::EventD(int d)
{
    m_d = !(d != 4 || NowUs() != (11 + 10));
}

void
SimulatorEventsTestCase::Eventfoo0()
{
}

void
SimulatorEventsTestCase::Destroy()
{
    if (m_destroyId.IsExpired())
    {
        m_destroy = true;
    }
}

void
SimulatorEventsTestCase::DoRun()
{
    m_a = true;
    m_b = false;
    m_c = true;
    m_d = false;

    Simulator::SetScheduler(m_schedulerFactory);

    EventId a = Simulator::Schedule(MicroSeconds(10), &SimulatorEventsTestCase::EventA, this, 1);
    Simulator::Schedule(MicroSeconds(11), &SimulatorEventsTestCase::EventB, this, 2);
    m_idC = Simulator::Schedule(MicroSeconds(12), &SimulatorEventsTestCase::EventC, this, 3);

    NS_TEST_EXPECT_MSG_EQ(!m_idC.IsExpired(), true, "");
    NS_TEST_EXPECT_MSG_EQ(!a.IsExpired(), true, "");
    Simulator::Cancel(a);
    NS_TEST_EXPECT_MSG_EQ(a.IsExpired(), true, "");
    Simulator::Run();
    NS_TEST_EXPECT_MSG_EQ(m_a, true, "Event A did not run ?");
    NS_TEST_EXPECT_MSG_EQ(m_b, true, "Event B did not run ?");
    NS_TEST_EXPECT_MSG_EQ(m_c, true, "Event C did not run ?");
    NS_TEST_EXPECT_MSG_EQ(m_d, true, "Event D did not run ?");

    EventId anId = Simulator::ScheduleNow(&SimulatorEventsTestCase::Eventfoo0, this);

    // Test copy assignment operator
    // NOLINTNEXTLINE(performance-unnecessary-copy-initialization)
    EventId anotherId = anId;

    NS_TEST_EXPECT_MSG_EQ(!(anId.IsExpired() || anotherId.IsExpired()),
                          true,
                          "Event should not have expired yet.");

    Simulator::Remove(anId);
    NS_TEST_EXPECT_MSG_EQ(anId.IsExpired(), true, "Event was removed: it is now expired");
    NS_TEST_EXPECT_MSG_EQ(anotherId.IsExpired(), true, "Event was removed: it is now expired");

    m_destroy = false;
    m_destroyId = Simulator::ScheduleDestroy(&SimulatorEventsTestCase::Destroy, this);
    NS_TEST_EXPECT_MSG_EQ(!m_destroyId.IsExpired(), true, "Event should not have expired yet");
    m_destroyId.Cancel();
    NS_TEST_EXPECT_MSG_EQ(m_destroyId.IsExpired(),
                          true,
                          "Event was canceled: should have expired now");

    m_destroyId = Simulator::ScheduleDestroy(&SimulatorEventsTestCase::Destroy, this);
    NS_TEST_EXPECT_MSG_EQ(!m_destroyId.IsExpired(), true, "Event should not have expired yet");
    Simulator::Remove(m_destroyId);
    NS_TEST_EXPECT_MSG_EQ(m_destroyId.IsExpired(),
                          true,
                          "Event was canceled: should have expired now");

    m_destroyId = Simulator::ScheduleDestroy(&SimulatorEventsTestCase::Destroy, this);
    NS_TEST_EXPECT_MSG_EQ(!m_destroyId.IsExpired(), true, "Event should not have expired yet");

    Simulator::Run();
    NS_TEST_EXPECT_MSG_EQ(!m_destroyId.IsExpired(), true, "Event should not have expired yet");
    NS_TEST_EXPECT_MSG_EQ(!m_destroy, true, "Event should not have run");

    Simulator::Destroy();
    NS_TEST_EXPECT_MSG_EQ(m_destroyId.IsExpired(), true, "Event should have expired now");
    NS_TEST_EXPECT_MSG_EQ(m_destroy, true, "Event should have run");
}

/**
 * \ingroup simulator-tests
 *
 * \brief Check that all templates are instantiated correctly.
 *
 * This is a compilation test, it cannot fail at runtime.
 */
class SimulatorTemplateTestCase : public TestCase
{
  public:
    SimulatorTemplateTestCase();
    /**
     * Ref and Unref - only here for testing of Ptr<>
     *
     * @{
     */
    void Ref() const {};
    void Unref() const {};
    /** @} */

  private:
    void DoRun() override;

    /**
     * Function used for scheduling.
     *
     * @{
     */
    void bar0(){};
    void bar1(int){};
    void bar2(int, int){};
    void bar3(int, int, int){};
    void bar4(int, int, int, int){};
    void bar5(int, int, int, int, int){};
    void baz1(int&){};
    void baz2(int&, int&){};
    void baz3(int&, int&, int&){};
    void baz4(int&, int&, int&, int&){};
    void baz5(int&, int&, int&, int&, int&){};
    void cbaz1(const int&){};
    void cbaz2(const int&, const int&){};
    void cbaz3(const int&, const int&, const int&){};
    void cbaz4(const int&, const int&, const int&, const int&){};
    void cbaz5(const int&, const int&, const int&, const int&, const int&){};

    void bar0c() const {};
    void bar1c(int) const {};
    void bar2c(int, int) const {};
    void bar3c(int, int, int) const {};
    void bar4c(int, int, int, int) const {};
    void bar5c(int, int, int, int, int) const {};
    void baz1c(int&) const {};
    void baz2c(int&, int&) const {};
    void baz3c(int&, int&, int&) const {};
    void baz4c(int&, int&, int&, int&) const {};
    void baz5c(int&, int&, int&, int&, int&) const {};
    void cbaz1c(const int&) const {};
    void cbaz2c(const int&, const int&) const {};
    void cbaz3c(const int&, const int&, const int&) const {};
    void cbaz4c(const int&, const int&, const int&, const int&) const {};
    void cbaz5c(const int&, const int&, const int&, const int&, const int&) const {};
    /** @} */
};

/**
 * Function used for scheduling.
 *
 * @{
 */
static void
foo0()
{
}

static void
foo1(int)
{
}

static void
foo2(int, int)
{
}

static void
foo3(int, int, int)
{
}

static void
foo4(int, int, int, int)
{
}

static void
foo5(int, int, int, int, int)
{
}

static void
ber1(int&)
{
}

static void
ber2(int&, int&)
{
}

static void
ber3(int&, int&, int&)
{
}

static void
ber4(int&, int&, int&, int&)
{
}

static void
ber5(int&, int&, int&, int&, int&)
{
}

static void
cber1(const int&)
{
}

static void
cber2(const int&, const int&)
{
}

static void
cber3(const int&, const int&, const int&)
{
}

static void
cber4(const int&, const int&, const int&, const int&)
{
}

static void
cber5(const int&, const int&, const int&, const int&, const int&)
{
}

/** @} */

SimulatorTemplateTestCase::SimulatorTemplateTestCase()
    : TestCase("Check that all templates are instantiated correctly. This is a compilation test, "
               "it cannot fail at runtime.")
{
}

void
SimulatorTemplateTestCase::DoRun()
{
    // Test schedule of const methods
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar0c, this);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar1c, this, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar2c, this, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar3c, this, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar4c, this, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar5c, this, 0, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz1c, this, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz2c, this, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz3c, this, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz4c, this, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz5c, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar0c, this);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar1c, this, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar2c, this, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar3c, this, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar4c, this, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar5c, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz1c, this, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz2c, this, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz3c, this, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz4c, this, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz5c, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar0c, this);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar1c, this, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar2c, this, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar3c, this, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar4c, this, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar5c, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz1c, this, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz2c, this, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz3c, this, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz4c, this, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz5c, this, 0, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz1c, this, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz2c, this, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz3c, this, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz4c, this, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz5c, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz1c, this, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz2c, this, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz3c, this, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz4c, this, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz5c, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz1c, this, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz2c, this, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz3c, this, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz4c, this, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz5c, this, 0, 0, 0, 0, 0);

    // Test of schedule const methods with Ptr<> pointers
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar0c,
                        Ptr<const SimulatorTemplateTestCase>(this));
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar1c,
                        Ptr<const SimulatorTemplateTestCase>(this),
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar2c,
                        Ptr<const SimulatorTemplateTestCase>(this),
                        0,
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar3c,
                        Ptr<const SimulatorTemplateTestCase>(this),
                        0,
                        0,
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar4c,
                        Ptr<const SimulatorTemplateTestCase>(this),
                        0,
                        0,
                        0,
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar5c,
                        Ptr<const SimulatorTemplateTestCase>(this),
                        0,
                        0,
                        0,
                        0,
                        0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar0c,
                           Ptr<const SimulatorTemplateTestCase>(this));
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar1c,
                           Ptr<const SimulatorTemplateTestCase>(this),
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar2c,
                           Ptr<const SimulatorTemplateTestCase>(this),
                           0,
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar3c,
                           Ptr<const SimulatorTemplateTestCase>(this),
                           0,
                           0,
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar4c,
                           Ptr<const SimulatorTemplateTestCase>(this),
                           0,
                           0,
                           0,
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar5c,
                           Ptr<const SimulatorTemplateTestCase>(this),
                           0,
                           0,
                           0,
                           0,
                           0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar0c,
                               Ptr<const SimulatorTemplateTestCase>(this));
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar1c,
                               Ptr<const SimulatorTemplateTestCase>(this),
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar2c,
                               Ptr<const SimulatorTemplateTestCase>(this),
                               0,
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar3c,
                               Ptr<const SimulatorTemplateTestCase>(this),
                               0,
                               0,
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar4c,
                               Ptr<const SimulatorTemplateTestCase>(this),
                               0,
                               0,
                               0,
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar5c,
                               Ptr<const SimulatorTemplateTestCase>(this),
                               0,
                               0,
                               0,
                               0,
                               0);

    // Test schedule of raw functions
    Simulator::Schedule(Seconds(0.0), &foo0);
    Simulator::Schedule(Seconds(0.0), &foo1, 0);
    Simulator::Schedule(Seconds(0.0), &foo2, 0, 0);
    Simulator::Schedule(Seconds(0.0), &foo3, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &foo4, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &foo5, 0, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &cber1, 0);
    Simulator::Schedule(Seconds(0.0), &cber2, 0, 0);
    Simulator::Schedule(Seconds(0.0), &cber3, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &cber4, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &cber5, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&foo0);
    Simulator::ScheduleNow(&foo1, 0);
    Simulator::ScheduleNow(&foo2, 0, 0);
    Simulator::ScheduleNow(&foo3, 0, 0, 0);
    Simulator::ScheduleNow(&foo4, 0, 0, 0, 0);
    Simulator::ScheduleNow(&foo5, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&cber1, 0);
    Simulator::ScheduleNow(&cber2, 0, 0);
    Simulator::ScheduleNow(&cber3, 0, 0, 0);
    Simulator::ScheduleNow(&cber4, 0, 0, 0, 0);
    Simulator::ScheduleNow(&cber5, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&foo0);
    Simulator::ScheduleDestroy(&foo1, 0);
    Simulator::ScheduleDestroy(&foo2, 0, 0);
    Simulator::ScheduleDestroy(&foo3, 0, 0, 0);
    Simulator::ScheduleDestroy(&foo4, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&foo5, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&cber1, 0);
    Simulator::ScheduleDestroy(&cber2, 0, 0);
    Simulator::ScheduleDestroy(&cber3, 0, 0, 0);
    Simulator::ScheduleDestroy(&cber4, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&cber5, 0, 0, 0, 0, 0);

    // Test schedule of normal member methods
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar0, this);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar1, this, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar2, this, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar3, this, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar4, this, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::bar5, this, 0, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz1, this, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz2, this, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz3, this, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz4, this, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::cbaz5, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar0, this);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar1, this, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar2, this, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar3, this, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar4, this, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar5, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz1, this, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz2, this, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz3, this, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz4, this, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::cbaz5, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar0, this);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar1, this, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar2, this, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar3, this, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar4, this, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar5, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz1, this, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz2, this, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz3, this, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz4, this, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::cbaz5, this, 0, 0, 0, 0, 0);

    // test schedule of normal methods with Ptr<> pointers
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar0,
                        Ptr<SimulatorTemplateTestCase>(this));
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar1,
                        Ptr<SimulatorTemplateTestCase>(this),
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar2,
                        Ptr<SimulatorTemplateTestCase>(this),
                        0,
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar3,
                        Ptr<SimulatorTemplateTestCase>(this),
                        0,
                        0,
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar4,
                        Ptr<SimulatorTemplateTestCase>(this),
                        0,
                        0,
                        0,
                        0);
    Simulator::Schedule(Seconds(0.0),
                        &SimulatorTemplateTestCase::bar5,
                        Ptr<SimulatorTemplateTestCase>(this),
                        0,
                        0,
                        0,
                        0,
                        0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar0, Ptr<SimulatorTemplateTestCase>(this));
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar1,
                           Ptr<SimulatorTemplateTestCase>(this),
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar2,
                           Ptr<SimulatorTemplateTestCase>(this),
                           0,
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar3,
                           Ptr<SimulatorTemplateTestCase>(this),
                           0,
                           0,
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar4,
                           Ptr<SimulatorTemplateTestCase>(this),
                           0,
                           0,
                           0,
                           0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::bar5,
                           Ptr<SimulatorTemplateTestCase>(this),
                           0,
                           0,
                           0,
                           0,
                           0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar0,
                               Ptr<SimulatorTemplateTestCase>(this));
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar1,
                               Ptr<SimulatorTemplateTestCase>(this),
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar2,
                               Ptr<SimulatorTemplateTestCase>(this),
                               0,
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar3,
                               Ptr<SimulatorTemplateTestCase>(this),
                               0,
                               0,
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar4,
                               Ptr<SimulatorTemplateTestCase>(this),
                               0,
                               0,
                               0,
                               0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::bar5,
                               Ptr<SimulatorTemplateTestCase>(this),
                               0,
                               0,
                               0,
                               0,
                               0);

    // the code below does not compile, as expected.
    // Simulator::Schedule (Seconds (0.0), &cber1, 0.0);

    // This code appears to be duplicate test code.
    Simulator::Schedule(Seconds(0.0), &ber1, 0);
    Simulator::Schedule(Seconds(0.0), &ber2, 0, 0);
    Simulator::Schedule(Seconds(0.0), &ber3, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &ber4, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &ber5, 0, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz1, this, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz2, this, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz3, this, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz4, this, 0, 0, 0, 0);
    Simulator::Schedule(Seconds(0.0), &SimulatorTemplateTestCase::baz5, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&ber1, 0);
    Simulator::ScheduleNow(&ber2, 0, 0);
    Simulator::ScheduleNow(&ber3, 0, 0, 0);
    Simulator::ScheduleNow(&ber4, 0, 0, 0, 0);
    Simulator::ScheduleNow(&ber5, 0, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz1, this, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz2, this, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz3, this, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz4, this, 0, 0, 0, 0);
    Simulator::ScheduleNow(&SimulatorTemplateTestCase::baz5, this, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&ber1, 0);
    Simulator::ScheduleDestroy(&ber2, 0, 0);
    Simulator::ScheduleDestroy(&ber3, 0, 0, 0);
    Simulator::ScheduleDestroy(&ber4, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&ber5, 0, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz1, this, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz2, this, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz3, this, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz4, this, 0, 0, 0, 0);
    Simulator::ScheduleDestroy(&SimulatorTemplateTestCase::baz5, this, 0, 0, 0, 0, 0);

    Simulator::Run();
    Simulator::Destroy();
}

/**
 * \ingroup simulator-tests
 *
 * \brief The simulator Test Suite.
 */
class SimulatorTransitionTestCase : public TestCase
{
  public:
    explicit SimulatorTransitionTestCase(ObjectFactory factory)
        : TestCase("Shifted pending events with " + factory.GetTypeId().GetName()),
          m_factory(factory)
    {
    }

  private:
    void Never()
    {
        NS_TEST_EXPECT_MSG_EQ(true, false, "Cancelled or removed event executed");
    }

    void Record(int value, int64_t timestamp)
    {
        NS_TEST_EXPECT_MSG_EQ(Simulator::Now().GetNanoSeconds(), timestamp, "Wrong effective timestamp");
        m_order.push_back(value);
    }

    void AfterFirstTransition()
    {
        Record(1, 5);
        NS_TEST_EXPECT_MSG_EQ(m_old.IsExpired(), false, "Shifted pending EventId became expired");
        NS_TEST_EXPECT_MSG_EQ(m_executed.IsExpired(), true, "Executed event was revived by a jump");
        NS_TEST_EXPECT_MSG_EQ(m_old.GetTs(), 20, "EventId historical timestamp changed");
        NS_TEST_EXPECT_MSG_EQ(Simulator::GetDelayLeft(m_old).GetNanoSeconds(), 115,
                              "Delay query ignored an unapplied queue transition");
        Simulator::Cancel(m_cancel);
        Simulator::Remove(m_remove);
        NS_TEST_EXPECT_MSG_EQ(m_cancel.IsExpired(), true, "Cancel failed after a jump");
        NS_TEST_EXPECT_MSG_EQ(m_remove.IsExpired(), true, "Remove failed after a jump");

        ObjectFactory replacement;
        replacement.SetTypeId(MapScheduler::GetTypeId());
        Simulator::SetScheduler(replacement);
        NS_TEST_EXPECT_MSG_EQ(Simulator::GetDelayLeft(m_old).GetNanoSeconds(), 115,
                              "Replacing the scheduler lost pending keys");

        std::thread producer([this]() {
            Simulator::ScheduleWithContext(77, NanoSeconds(30),
                &SimulatorTransitionTestCase::ContextEvent, this);
        });
        producer.join();
        Simulator::Schedule(NanoSeconds(10), &SimulatorTransitionTestCase::SecondTransition, this);
    }

    void ContextEvent()
    {
        Record(3, 85);
        NS_TEST_EXPECT_MSG_EQ(Simulator::GetContext(), 77, "Cross-thread event lost its context");
    }

    void FirstTransition()
    {
        transition_delay.push_back(100);
        ++transition_cnt;
        // A new-generation event is earlier than all shifted old-generation
        // events. The scheduler must be reordered before selecting either.
        Simulator::ScheduleNow(&SimulatorTransitionTestCase::AfterFirstTransition, this);
    }

    void SecondTransition()
    {
        transition_delay.push_back(50);
        ++transition_cnt;
        NS_TEST_EXPECT_MSG_EQ(Simulator::GetDelayLeft(m_old).GetNanoSeconds(), 155,
                              "Second pending transition was not included in the delay");
        Simulator::ScheduleNow(&SimulatorTransitionTestCase::Record, this, 2, 15);
    }

    void DestroyEvent()
    {
        m_destroyed = true;
    }

    void SharedCallback()
    {
        ++m_sharedCount;
        NS_TEST_EXPECT_MSG_EQ(m_sharedFirst.IsExpired(), true, "Popped UID remained pending");
        NS_TEST_EXPECT_MSG_EQ(m_sharedSecond.IsExpired(), m_sharedCount == 2,
                              "Executing one UID changed another UID sharing its EventImpl");
    }

    void DoRun() override
    {
        transition_cnt = 0;
        transition_delay.clear();
        Simulator::SetScheduler(m_factory);
        m_executed = Simulator::Schedule(NanoSeconds(1), []() {});
        Simulator::Schedule(NanoSeconds(5), &SimulatorTransitionTestCase::FirstTransition, this);
        m_old = Simulator::Schedule(NanoSeconds(20), &SimulatorTransitionTestCase::Record, this, 4, 170);
        Simulator::Schedule(NanoSeconds(20), &SimulatorTransitionTestCase::Record, this, 5, 170);
        m_cancel = Simulator::Schedule(NanoSeconds(25), &SimulatorTransitionTestCase::Never, this);
        m_remove = Simulator::Schedule(NanoSeconds(30), &SimulatorTransitionTestCase::Never, this);
        const auto destroy = Simulator::ScheduleDestroy(&SimulatorTransitionTestCase::DestroyEvent, this);
        Simulator::Run();
        NS_TEST_EXPECT_MSG_EQ(m_order.size(), 5, "Missing or duplicate callbacks");
        for (std::size_t i = 0; i < m_order.size(); ++i)
        {
            NS_TEST_EXPECT_MSG_EQ(m_order[i], static_cast<int>(i + 1), "Timestamp/UID order was not preserved");
        }
        NS_TEST_EXPECT_MSG_EQ(m_old.IsExpired(), true, "Completed event remains pending");
        NS_TEST_EXPECT_MSG_EQ(destroy.IsExpired(), false, "Destroy events entered the normal pending registry");

        // Empty-queue transitions and a second Run must not reuse stale keys.
        Simulator::ScheduleNow(&SimulatorTransitionTestCase::Record, this, 6, 200);
        transition_delay.push_back(25);
        ++transition_cnt;
        Simulator::Run();
        NS_TEST_EXPECT_MSG_EQ(m_order.back(), 6, "Event after empty queue was lost");
        Ptr<EventImpl> shared(MakeEvent(&SimulatorTransitionTestCase::SharedCallback, this), false);
        m_sharedFirst = Simulator::Schedule(NanoSeconds(10), shared);
        m_sharedSecond = Simulator::Schedule(NanoSeconds(20), shared);
        Simulator::Run();
        NS_TEST_EXPECT_MSG_EQ(m_sharedCount, 2, "Shared EventImpl lost an independently queued UID");
        Simulator::Destroy();
        NS_TEST_EXPECT_MSG_EQ(m_destroyed, true, "Destroy event was not executed");
        NS_TEST_EXPECT_MSG_EQ(destroy.IsExpired(), true, "Destroy event remained alive");
        transition_cnt = 0;
        transition_delay.clear();
    }

    ObjectFactory m_factory;
    EventId m_old, m_cancel, m_remove, m_executed;
    EventId m_sharedFirst, m_sharedSecond;
    int m_sharedCount{0};
    std::vector<int> m_order;
    bool m_destroyed{false};
};

class SimulatorCancelHookImpl : public DefaultSimulatorImpl
{
  public:
    EventId target;
    bool wasRunning{false};
    Time delay;

    void PreEventHook(const EventId& id) override
    {
        if (id.GetUid() == target.GetUid())
        {
            wasRunning = !id.IsExpired();
            delay = Simulator::GetDelayLeft(id);
            Simulator::Cancel(id);
        }
    }
};

class SimulatorCancelHookTestCase : public TestCase
{
  public:
    SimulatorCancelHookTestCase()
        : TestCase("PreEventHook can inspect and cancel the event about to run")
    {
    }

  private:
    void DoRun() override
    {
        auto implementation = CreateObject<SimulatorCancelHookImpl>();
        Simulator::SetImplementation(implementation);
        bool executed = false;
        implementation->target = Simulator::Schedule(NanoSeconds(7), [&executed]() { executed = true; });
        Simulator::Run();
        NS_TEST_EXPECT_MSG_EQ(implementation->wasRunning, true, "Hook saw its future event as expired");
        NS_TEST_EXPECT_MSG_EQ(implementation->delay, NanoSeconds(7), "Hook lost the current event delay");
        NS_TEST_EXPECT_MSG_EQ(executed, false, "Hook could not cancel its current event");
        Simulator::Destroy();
    }
};

class SimulatorTestSuite : public TestSuite
{
  public:
    SimulatorTestSuite()
        : TestSuite("simulator")
    {
        ObjectFactory factory;
        factory.SetTypeId(ListScheduler::GetTypeId());

        AddTestCase(new SimulatorEventsTestCase(factory), TestCase::QUICK);
        AddTestCase(new SimulatorTransitionTestCase(factory), TestCase::QUICK);
        factory.SetTypeId(MapScheduler::GetTypeId());
        AddTestCase(new SimulatorEventsTestCase(factory), TestCase::QUICK);
        AddTestCase(new SimulatorTransitionTestCase(factory), TestCase::QUICK);
        factory.SetTypeId(HeapScheduler::GetTypeId());
        AddTestCase(new SimulatorEventsTestCase(factory), TestCase::QUICK);
        AddTestCase(new SimulatorTransitionTestCase(factory), TestCase::QUICK);
        factory.SetTypeId(CalendarScheduler::GetTypeId());
        AddTestCase(new SimulatorEventsTestCase(factory), TestCase::QUICK);
        AddTestCase(new SimulatorTransitionTestCase(factory), TestCase::QUICK);
        factory.SetTypeId(PriorityQueueScheduler::GetTypeId());
        AddTestCase(new SimulatorEventsTestCase(factory), TestCase::QUICK);
        AddTestCase(new SimulatorTransitionTestCase(factory), TestCase::QUICK);
        AddTestCase(new SimulatorCancelHookTestCase(), TestCase::QUICK);
    }
};

static SimulatorTestSuite g_simulatorTestSuite; //!< Static variable for test initialization
