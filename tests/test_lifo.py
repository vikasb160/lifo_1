import os
import random
from pathlib import Path

import cocotb
from cocotb import start_soon
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, NextTimeStep, ReadOnly, RisingEdge, Timer
from cocotb_tools.runner import get_runner

@cocotb.test()
async def example_test(dut):
    pass

def test_lifo_runner():
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