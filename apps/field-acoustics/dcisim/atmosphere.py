"""Atmospheric sound absorption, ISO 9613-1.

Returns pure-tone attenuation coefficients in dB/m. Over a 100 m throw the
8 kHz band loses several dB to air alone, which is a meaningful part of why a
hornline sounds darker from the back of the stands than from row 5.
"""

import numpy as np

# Octave band centres used throughout the simulator.
BANDS = np.array([63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0])

# A-weighting corrections at those band centres (IEC 61672).
A_WEIGHT = np.array([-26.2, -16.1, -8.6, -3.2, 0.0, 1.2, 1.0, -1.1])

T0 = 293.15  # reference air temperature, K
T01 = 273.16  # triple-point isotherm, K
PR = 101.325  # reference ambient pressure, kPa


def absorption_coefficients(freqs=BANDS, temp_c=24.0, humidity_pct=55.0, pressure_kpa=PR):
    """Atmospheric attenuation in dB/m for each frequency in `freqs`.

    Defaults are a warm, moderately humid summer evening -- roughly finals week
    in Indianapolis. Dry air absorbs high frequencies much more aggressively, so
    this is worth setting to match your actual show site.
    """
    # Below absolute zero the relaxation terms raise a negative base to a
    # fractional power. Python floats answer that with a complex number, which
    # then silently casts back to a plausible-looking real further downstream --
    # so reject it here rather than return convincing garbage.
    if not -60.0 <= temp_c <= 60.0:
        raise ValueError("temperature %.1f C is outside the modelled range "
                         "(-60 to 60 C)" % temp_c)
    if not 0.0 <= humidity_pct <= 100.0:
        raise ValueError("relative humidity must be 0-100%%, got %.1f" % humidity_pct)
    if pressure_kpa <= 0.0:
        raise ValueError("ambient pressure must be positive, got %.1f kPa" % pressure_kpa)

    f = np.asarray(freqs, dtype=float)
    T = temp_c + 273.15
    pa = pressure_kpa

    # Molar concentration of water vapour, in percent.
    psat_ratio = 10.0 ** (-6.8346 * (T01 / T) ** 1.261 + 4.6151)
    h = humidity_pct * psat_ratio / (pa / PR)

    # Relaxation frequencies of oxygen and nitrogen.
    fr_o = (pa / PR) * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))
    fr_n = (pa / PR) * (T / T0) ** -0.5 * (
        9.0 + 280.0 * h * np.exp(-4.170 * ((T / T0) ** (-1.0 / 3.0) - 1.0))
    )

    relaxation = (T / T0) ** -2.5 * (
        0.01275 * np.exp(-2239.1 / T) / (fr_o + f**2 / fr_o)
        + 0.1068 * np.exp(-3352.0 / T) / (fr_n + f**2 / fr_n)
    )
    classical = 1.84e-11 * (pa / PR) ** -1.0 * (T / T0) ** 0.5

    return 8.686 * f**2 * (classical + relaxation)


def speed_of_sound(temp_c=24.0):
    """Speed of sound in m/s for dry air at the given temperature."""
    if temp_c <= -273.15:
        raise ValueError("temperature %.1f C is below absolute zero" % temp_c)
    return 331.3 * np.sqrt(1.0 + temp_c / 273.15)
