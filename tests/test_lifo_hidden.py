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
    runner.test(hdl_toplevel="lifo", test_module="test_lifo_hidden_runner")