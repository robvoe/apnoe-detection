import cmath
import math
from typing import List, NamedTuple, Optional
from enum import Enum

import numpy
import numpy as np
import numba


class PeakType(Enum):
    Minimum = 0
    Maximum = 1


class ZeroCrossType(Enum):
    Positive = 0
    Negative = 1


Peak = NamedTuple("Peak", type=PeakType, extreme_value=float, start=int, end=int)
ZeroCross = NamedTuple("ZeroCross", type=ZeroCrossType, position=int)


@numba.jit(nopython=True)
def get_peaks(waveform: np.ndarray, filter_kernel_width: int) -> List[Peak]:
    """
    Detects min/max peaks of a around-zero centered waveform.

    :param waveform: Input waveform. Must be centered around zero.
    :param filter_kernel_width: Width of the filter kernel. Most likely the number
                                of samples that form one signal period.
    :return:
    """
    # Convolve waveform with the filter kernel & cut the right and left overlaps
    filter_kernel = np.ones(filter_kernel_width) / filter_kernel_width
    filtered_waveform = np.convolve(waveform, filter_kernel)
    filtered_waveform = filtered_waveform[int(filter_kernel_width/2) - 1:-math.ceil(filter_kernel_width/2)]
    if len(filtered_waveform) != len(waveform):
        raise AssertionError(f"There is a length mismatch in filtered and original waveform. Needs some rework!")

    # Align our filtered waveform with the original signal
    shift = int(-filter_kernel_width / 4)
    if shift != 0:
        filtered_waveform = np.roll(filtered_waveform, shift=shift)
        filtered_waveform[shift:] = np.nan

    zero_crosses_pos: np.ndarray = np.where(np.diff(np.sign(filtered_waveform)) > 1)[0]
    zero_crosses_neg: np.ndarray = np.where(np.diff(np.sign(filtered_waveform)) < -1)[0]
    if np.abs(len(zero_crosses_pos)-len(zero_crosses_neg)) > 1:
        raise AssertionError("There's a discrepancy in numbers of detected pos/neg zero crosses. Needs some rework!")

    peaks: List[Peak] = []
    if len(zero_crosses_pos) == 0 or len(zero_crosses_neg) == 0:
        return peaks

    # Merge our zero crosses into one list & do some sanity checks
    zero_crosses: List[ZeroCross] = []
    last_zero_cross_type: Optional[ZeroCrossType] = None
    while len(zero_crosses_pos) != 0 or len(zero_crosses_neg) != 0:
        position_pos = zero_crosses_pos[0] if len(zero_crosses_pos) != 0 else None
        position_neg = zero_crosses_neg[0] if len(zero_crosses_neg) != 0 else None
        if position_neg is None or (position_pos is not None and position_pos < position_neg):
            if last_zero_cross_type is not None and last_zero_cross_type == ZeroCrossType.Positive:
                raise AssertionError("Consecutive positive zero crosses of the same type are not supported!")
            zero_crosses.append(ZeroCross(type=ZeroCrossType.Positive, position=position_pos))
            zero_crosses_pos = zero_crosses_pos[1:]
            last_zero_cross_type = ZeroCrossType.Positive
        else:
            if last_zero_cross_type is not None and last_zero_cross_type == ZeroCrossType.Negative:
                raise AssertionError("Consecutive negative zero crosses of the same type are not supported!")
            zero_crosses.append(ZeroCross(type=ZeroCrossType.Negative, position=position_neg))
            zero_crosses_neg = zero_crosses_neg[1:]
            last_zero_cross_type = ZeroCrossType.Negative

    # Now, let's create the list of peaks
    last_zero_cross: Optional[ZeroCross] = None
    for zero_cross in zero_crosses:
        if last_zero_cross is None:
            last_zero_cross = zero_cross
            continue
        if zero_cross.type == ZeroCrossType.Positive:
            extreme_value = np.min(waveform[last_zero_cross.position:zero_cross.position])
            peak_type = PeakType.Minimum
        else:
            extreme_value = np.max(waveform[last_zero_cross.position:zero_cross.position])
            peak_type = PeakType.Maximum
        peaks.append(Peak(type=peak_type, extreme_value=extreme_value, start=last_zero_cross.position, end=zero_cross.position-1))
        last_zero_cross = zero_cross
    return peaks


def test_qualitative():
    import matplotlib.pyplot as plt
    T = 4*np.pi
    f_s = 10
    x = np.arange(T*f_s)
    y = np.sin(x/f_s)

    # --------------------- Make some dev-helping plots. Code was (almost) entirely taken from the function above.
    filter_size = int(f_s)
    # filter = np.append(-np.ones(filter_size), np.ones(filter_size)) / filter_size
    filter = np.ones(filter_size) / filter_size
    filtered_waveform = np.convolve(y, filter)
    filtered_waveform = filtered_waveform[int(filter_size/2) - 1:-math.ceil(filter_size/2)]
    if len(filtered_waveform) != len(y):
        raise AssertionError(f"There is a length mismatch in filtered and original waveform. Needs some rework!")

    # Align our filtered waveform with the original signal
    shift = int(-filter_size/4)
    if shift != 0:
        filtered_waveform = np.roll(filtered_waveform, shift=shift)
        filtered_waveform[shift:] = np.nan

    plt.plot(y)
    plt.plot(filtered_waveform)
    plt.show()
    # --------------

    peaks = get_peaks(waveform=y, filter_kernel_width=int(f_s))

    assert len(peaks) == 2
    assert peaks[0].type == PeakType.Minimum
    assert peaks[1].type == PeakType.Maximum
    pass


def test_jit_speed():
    from datetime import datetime
    import os.path

    sample_signal = numpy.load(file=os.path.dirname(os.path.realpath(__file__))+"/sample_signal.npy")
    get_peaks(waveform=sample_signal, filter_kernel_width=5)  # One initial run to JIT the code

    n_runs = 5000
    started_at = datetime.now()
    for n in range(n_runs):
        result = get_peaks(waveform=sample_signal, filter_kernel_width=50)
    overall_seconds = (datetime.now()-started_at).total_seconds()

    print()
    print(f"The whole process with n_runs={n_runs} took {overall_seconds*1000:.1f}ms")
    print(f"A single run took {overall_seconds/n_runs*1000:.2f}ms")


def test_example_plot():
    import os.path
    import pandas as pd
    import matplotlib.pyplot as plt

    sample_signal = numpy.load(file=os.path.dirname(os.path.realpath(__file__)) + "/sample_signal.npy")
    peaks = get_peaks(waveform=sample_signal, filter_kernel_width=5)
    peaks_mat = np.zeros(shape=(sample_signal.shape[0],))
    for p in peaks:
        peaks_mat[int(p.start + (p.end - p.start) / 2)] = p.extreme_value

    sample_signal_series = pd.Series(sample_signal)
    peaks_series = pd.Series(peaks_mat)
    df = pd.concat([sample_signal_series, peaks_series], axis=1)

    df.plot(figsize=(15, 6), subplots=False)
    plt.show()
