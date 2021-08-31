"""
functions to make a double gate map
works with Keithley 2600, Oxford Triton and Zurich Instrument
MFLI lock-in amplifiers
"""

import time
from typing import Optional
from tqdm.auto import tqdm

from qcodes import Station, Instrument, Parameter
from qcodes.instrument.channel import InstrumentChannel
from qcodes.dataset.experiment_container import Experiment

import zhinst.qcodes

from ..instrument.instrument_tools import create_instrument, add_to_station
from ..instrument.keithley import initialise_keithley
from ..measurement.array import generate_1D_sweep_array
from ..measurement.sweep import sweep2d


def station_triton(
    keithley_addr: str,
    triton_addr: str,
    *MFLI_num: str,
    current_range: Optional[float] = 10e-9
):
    """ functions to initialise the station for that measurement """

    station = Station()
    from qcodes.instrument_drivers.tektronix.Keithley_2600_channels import \
        Keithley_2600
    keithley = create_instrument(Keithley_2600, "keithley",
                                 address=keithley_addr,
                                 force_new_instance=True)
    add_to_station(keithley, station)

    from qcodes.instrument_drivers.oxford.triton import Triton
    triton = create_instrument(Triton, "triton", address=triton_addr,
                               port=33576, force_new_instance=True)
    add_to_station(triton, station)

    from zhinst.qcodes import MFLI

    for mf in list(MFLI_num):
        num = str(mf)
        locals()['mf' + num] = create_instrument(MFLI, 'mf' + num,
                                                 'dev' + num,
                                                 force_new_instance=True)
        add_to_station(locals()['mf' + num], station)

    curr_range = Parameter('current_range', label='current range',
                           unit='A/V', set_cmd=None, get_cmd=None)
    curr_range.set(current_range)
    add_to_station(curr_range, station)

    return station


def _go_to(v0, v1,
           channel: InstrumentChannel,
           desc: Optional[str] = None,
           threshold: Optional[float] = None
           ):
    array = generate_1D_sweep_array(v0, v1, step=2e-1)
    time.sleep(.5)
    for v in tqdm(array, leave=False, desc=desc):
        channel.volt(v)
        channel.curr()
        time.sleep(0.1)
        if threshold and channel.curr() > threshold:
            break
    time.sleep(.5)
    return v


def gate_map(
    xarray,
    inner_delay,
    yarray, outer_delay,
    station: Station,
    exp: Optional[Experiment] = None,
    label: Optional[str] = None,
    measure_retrace: Optional[bool] = False,
):

    initialise_keithley(station)
    # NOTE: this does not take into account any change in the compliance limit.
    # limits that were previously set up will be overwritten at that point.
    # TODO: make the function useable with different kinds of keithleys

    lockins = []
    for name, itm in station.components.items():
        if isinstance(itm, Instrument):
            if itm.__class__ == zhinst.qcodes.mfli.MFLI:
                lockins.append(name)
    init_tg = station.keithley.smua.volt()
    init_bg = station.keithley.smub.volt()

    _go_to(init_tg, xarray[0], station.keithley.smua,
           desc=f'sweeping top gate to {init_tg} V')

    _go_to(init_bg, yarray[0], station.keithley.smub,
           desc=f'sweeping back gate to {init_bg} V')

    raw_data = sweep2d(
        station.keithley.smua.volt,
        xarray,
        inner_delay,
        station.keithley.smub.volt,
        yarray,
        outer_delay,
        *tuple(station.__getattr__(lockin).demods[0].sample
               for lockin in lockins),
        station.triton.T8,
        station.triton.Bz,
        station.keithley.smua.curr,
        station.keithley.smub.curr,
        exp=exp,
        measurement_name=f'gate map {label}',
        use_threads=True,
        measure_retrace=measure_retrace,
    )

    return raw_data
