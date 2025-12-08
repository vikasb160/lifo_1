# test_lifo.py
import os
import random
from pathlib import Path
from cocotb_tools.runner import get_runner
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

DEPTH = int(os.getenv("DEPTH", 12))
DATA_WIDTH = int(os.getenv("DATA_WIDTH", 8))
CLK_PERIOD_NS = int(os.getenv("CLK_PERIOD_NS", 20))
SIM_TIMEOUT_NS = int(os.getenv("SIM_TIMEOUT_NS", 100000))

SHORT_DELAY = Timer(1, units="ns")


@cocotb.test()
async def lifo_random_op_test(dut):

    lifo_expected = []
    err_cnt = 0

    seed_env = os.getenv("SEED")
    if seed_env is not None:
        seed = int(seed_env)
        random.seed(seed)
        dut._log.info(f"Using SEED={seed}")

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS / 2, units="ns").start())

    # Reset
    dut.rst.value = 1
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.data_wr.value = 0

    await Timer(100, units="ns")
    dut.rst.value = 0
    await Timer(100, units="ns")

    async def do_write(wr_data_list):
        nonlocal err_cnt, lifo_expected

        for val in wr_data_list:
            await RisingEdge(dut.clk)
            dut.wr_en.value = 1
            dut.data_wr.value = val & ((1 << DATA_WIDTH) - 1)
            await SHORT_DELAY

            if len(lifo_expected) < DEPTH:
                if not int(dut.lifo_full.value):
                    lifo_expected.append(val)
                    dut._log.info(f"Write {val}, entry={len(lifo_expected)}")
                else:
                    err_cnt += 1
                    dut._log.error("lifo_full asserted incorrectly")
            else:
                if int(dut.lifo_full.value):
                    dut._log.info("Correct full flag")
                else:
                    err_cnt += 1
                    dut._log.error("lifo_full NOT asserted when full")

        await RisingEdge(dut.clk)
        dut.wr_en.value = 0
        dut.data_wr.value = 0

    async def do_read(count):
        nonlocal err_cnt, lifo_expected

        await RisingEdge(dut.clk)
        dut.rd_en.value = 1

        for _ in range(count):
            await RisingEdge(dut.clk)

            if len(lifo_expected) > 0:
                if int(dut.lifo_empty.value):
                    err_cnt += 1
                    dut._log.error("lifo_empty asserted incorrectly")

                await SHORT_DELAY
                act = int(dut.data_rd.value)
                exp = lifo_expected.pop()

                if act == exp:
                    dut._log.info(f"Read {act}, entry={len(lifo_expected)}")
                else:
                    err_cnt += 1
                    dut._log.error(f"Mismatch: ACT={act}, EXP={exp}")
            else:
                if not int(dut.lifo_empty.value):
                    err_cnt += 1
                    dut._log.error("lifo_empty not asserted when empty")
                else:
                    dut._log.info("Correct empty flag")

        dut.rd_en.value = 0

    async def do_simultaneous_read_write(wr_data_list):
        nonlocal err_cnt, lifo_expected

        if not wr_data_list:
            return

        # Behaviour derived from old InputMonitor:
        # During simultaneous read/write, depth stays the same but data_rd
        # should match the data written in that cycle (or previous one,
        # depending on DUT semantics). Here we enforce "match last written".
        exp_wr = wr_data_list.pop(0)

        await RisingEdge(dut.clk)
        dut.rd_en.value = 1
        dut.wr_en.value = 1
        dut.data_wr.value = exp_wr

        while wr_data_list:
            await RisingEdge(dut.clk)
            await SHORT_DELAY

            act = int(dut.data_rd.value)
            if act != exp_wr:
                err_cnt += 1
                dut._log.error(f"Simul mismatch ACT={act} EXP={exp_wr}")
            else:
                dut._log.info(f"Simul read/write {act}")

            exp_wr = wr_data_list.pop(0)
            dut.data_wr.value = exp_wr

        await RisingEdge(dut.clk)
        dut.wr_en.value = 0
        dut.rd_en.value = 0
        await SHORT_DELAY

        act = int(dut.data_rd.value)
        if act != exp_wr:
            err_cnt += 1
            dut._log.error(f"Final simul mismatch ACT={act}, EXP={exp_wr}")

    TEST_WEIGHT = int(os.getenv("TEST_WEIGHT", 1))

    for _ in range(TEST_WEIGHT):
        lifo_expected = []

        i = DEPTH
        while i > 0:
            op_sel = random.randrange(0, 3)
            op_count = random.randrange(1, i + 1)
            i -= op_count

            if op_sel == 0:
                dut._log.info(f"Read {op_count} times")
                await do_read(op_count)

            elif op_sel == 1:
                wr_list = [random.randrange(0, 2**DATA_WIDTH) for _ in range(op_count)]
                dut._log.info(f"Write {op_count} times")
                await do_write(wr_list)

            else:
                wr_list = [random.randrange(0, 2**DATA_WIDTH) for _ in range(op_count)]
                dut._log.info(f"Simultaneous RW {op_count} times")
                await do_simultaneous_read_write(wr_list)

        await Timer(1000, units="ns")

    # ---------- FINAL ASSERT ----------
    assert err_cnt == 0, f"TEST FAILED: {err_cnt} error(s) detected"

    dut._log.info("TEST PASSED")


# -------------------------------------------------------------------
#  LEGACY-STYLE RANDOM TEST 
# -------------------------------------------------------------------
@cocotb.test()
async def lifo_legacy_random_op_test(dut):
    """
    Port of the old 'lifo_rand_op_test' to the new style:

    - Same idea: random sequence of operations.
    - op_sel in {0, 1} where:
        0 -> write
        1 -> read
      (like the old OutputDriver._driver_send)
    - op_count limited to 1..5, mirroring the old code.
    - Uses local scoreboard and final assert instead of global err_cnt.
    """

    lifo_expected = []
    err_cnt = 0

    seed_env = os.getenv("SEED")
    if seed_env is not None:
        seed = int(seed_env)
        random.seed(seed)
        dut._log.info(f"[LEGACY] Using SEED={seed}")

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS / 2, units="ns").start())

    # Reset (same style as new test)
    dut.rst.value = 1
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.data_wr.value = 0

    await Timer(100, units="ns")
    dut.rst.value = 0
    await Timer(100, units="ns")

    async def do_write(wr_data_list):
        nonlocal err_cnt, lifo_expected

        for val in wr_data_list:
            await RisingEdge(dut.clk)
            dut.wr_en.value = 1
            dut.data_wr.value = val & ((1 << DATA_WIDTH) - 1)
            await SHORT_DELAY

            if len(lifo_expected) < DEPTH:
                if not int(dut.lifo_full.value):
                    lifo_expected.append(val)
                    dut._log.info(f"[LEGACY] Write {val}, entry={len(lifo_expected)}")
                else:
                    err_cnt += 1
                    dut._log.error("[LEGACY] lifo_full asserted incorrectly")
            else:
                if int(dut.lifo_full.value):
                    dut._log.info("[LEGACY] Correct full flag")
                else:
                    err_cnt += 1
                    dut._log.error("[LEGACY] lifo_full NOT asserted when full")

        await RisingEdge(dut.clk)
        dut.wr_en.value = 0
        dut.data_wr.value = 0

    async def do_read(count):
        nonlocal err_cnt, lifo_expected

        await RisingEdge(dut.clk)
        dut.rd_en.value = 1

        for _ in range(count):
            await RisingEdge(dut.clk)

            if len(lifo_expected) > 0:
                if int(dut.lifo_empty.value):
                    err_cnt += 1
                    dut._log.error("[LEGACY] lifo_empty asserted incorrectly")

                await SHORT_DELAY
                act = int(dut.data_rd.value)
                exp = lifo_expected.pop()

                if act == exp:
                    dut._log.info(f"[LEGACY] Read {act}, entry={len(lifo_expected)}")
                else:
                    err_cnt += 1
                    dut._log.error(f"[LEGACY] Mismatch: ACT={act}, EXP={exp}")
            else:
                if not int(dut.lifo_empty.value):
                    err_cnt += 1
                    dut._log.error("[LEGACY] lifo_empty not asserted when empty")
                else:
                    dut._log.info("[LEGACY] Correct empty flag")

        dut.rd_en.value = 0

    TEST_WEIGHT = int(os.getenv("TEST_WEIGHT", 1))

    for _ in range(TEST_WEIGHT):
        lifo_expected = []

        # This loop mirrors the structure of the old test:
        # i starts at DEPTH and we keep subtracting op_count until we hit 0 or below.
        i = DEPTH
        while i > 0:
            op_sel = random.randint(0, 1)      # 0: write, 1: read (like old code)
            op_count = random.randint(1, 5)    # 1..5 as in old test
            op_count = min(op_count, i)        # avoid negative, but keep behaviour similar
            i -= op_count

            if op_sel == 0:
                wr_list = [random.randrange(0, 2**DATA_WIDTH) for _ in range(op_count)]
                dut._log.info(f"[LEGACY] Write {op_count} times")
                await do_write(wr_list)
            else:
                dut._log.info(f"[LEGACY] Read {op_count} times")
                await do_read(op_count)

        await Timer(1000, units="ns")

    assert err_cnt == 0, f"[LEGACY] TEST FAILED: {err_cnt} error(s) detected"
    dut._log.info("[LEGACY] TEST PASSED")

@cocotb.test()
async def lifo_flag_behavior_test(dut):
    """
    Pure flag-only test.
    Verifies correct behavior of:
      - lifo_empty
      - lifo_full
      - transition rules:
            * empty when pointer == 0
            * full only when pointer == DEPTH-1 AND wr_op
            * full clears on any rd_op
    No data checking.
    """

    # start clock
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS / 2, units="ns").start())

    # RESET
    dut.rst.value = 1
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.data_wr.value = 0
    await Timer(100, units="ns")

    dut.rst.value = 0
    await Timer(50, units="ns")

    # After reset:
    assert int(dut.lifo_empty.value) == 1, "Should be EMPTY after reset"
    assert int(dut.lifo_full.value) == 0, "Should NOT be FULL after reset"

    # -----------------------------------------------
    # 1) PUSH until full
    # -----------------------------------------------
    for i in range(DEPTH):
        dut.wr_en.value = 1
        dut.rd_en.value = 0
        dut.data_wr.value = i & ((1 << DATA_WIDTH) - 1)

        await RisingEdge(dut.clk)
        await SHORT_DELAY

        # Empty only true at beginning
        if i == 0:
            assert int(dut.lifo_empty.value) == 0, "empty should become 0 after first push"

        # Full should assert ONLY on last push
        if i == DEPTH - 1:
            assert int(dut.lifo_full.value) == 1, "full MUST assert when pointer==DEPTH-1 and wr_op"
        else:
            assert int(dut.lifo_full.value) == 0, f"full must NOT assert early (i={i})"

    dut.wr_en.value = 0

    # -----------------------------------------------
    # 2) POP until empty
    # -----------------------------------------------
    for i in range(DEPTH):
        dut.rd_en.value = 1
        dut.wr_en.value = 0

        await RisingEdge(dut.clk)
        await SHORT_DELAY

        # Full must clear on ANY read
        assert int(dut.lifo_full.value) == 0, "full must clear on rd_op"

        # Empty must not assert until final read
        if i == DEPTH - 1:
            assert int(dut.lifo_empty.value) == 1, "empty MUST assert when pointer returns to 0"
        else:
            assert int(dut.lifo_empty.value) == 0, f"empty must NOT assert early (i={i})"

    dut.rd_en.value = 0

    # -----------------------------------------------
    # 3) Simultaneous read/write must NOT generate full or empty glitches
    # -----------------------------------------------
    # Push twice (to get pointer = 2)
    for k in range(2):
        dut.wr_en.value = 1
        dut.rd_en.value = 0
        dut.data_wr.value = k
        await RisingEdge(dut.clk)
        await SHORT_DELAY
    dut.wr_en.value = 0
    assert int(dut.lifo_empty.value) == 0

    # Do bypass cycles
    dut._log.info("Testing simultaneous read/write flag stability")

    for _ in range(5):
        dut.wr_en.value = 1
        dut.rd_en.value = 1
        dut.data_wr.value = random.randrange(0, (1 << DATA_WIDTH))

        await RisingEdge(dut.clk)
        await SHORT_DELAY

        # Full must ALWAYS be 0 because rd_op is active
        assert int(dut.lifo_full.value) == 0, "full must clear during bypass cycles"

        # Empty must stay 0 because pointer>0
        assert int(dut.lifo_empty.value) == 0, "empty must not assert during bypass"

    dut.wr_en.value = 0
    dut.rd_en.value = 0

    dut._log.info("FLAG BEHAVIOR TEST PASSED")

def test_lifo_hidden_runner():
    sim = os.getenv("SIM", "icarus")

    proj_path = Path(__file__).resolve().parent.parent

    sources = [proj_path / "sources/lifo.v"]

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel="lifo",
        always=True,
    )
    runner.test(hdl_toplevel="lifo", test_module="test_lifo_hidden")