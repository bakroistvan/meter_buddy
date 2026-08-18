import matplotlib.pyplot as plt
import numpy as np

# ADC-volt → SoC (matches battery::estimatePercent).
OCV = np.array(
    [
        [4.05, 100],
        [3.994, 95],
        [3.938, 90],
        [3.908, 85],
        [3.890, 80],
        [3.872, 75],
        [3.853, 70],
        [3.834, 65],
        [3.811, 60],
        [3.794, 55],
        [3.775, 50],
        [3.758, 45],
        [3.737, 40],
        [3.714, 35],
        [3.690, 30],
        [3.634, 25],
        [3.593, 20],
        [3.582, 15],
        [3.549, 10],
        [3.482, 5],
        [3.26, 0],
    ]
)

volts = np.linspace(3.26, 4.20, 200)
legacy = (volts - 3.30) * 100.0 / (4.20 - 3.30)
ocv_pct = np.interp(volts, OCV[::-1, 0], OCV[::-1, 1])

plt.figure(figsize=(8, 5))
plt.plot(volts, legacy, label="Legacy linear 3.30–4.20", color="#6b7280", linestyle="--", linewidth=1.8)
plt.plot(volts, ocv_pct, label="Firmware ADC-volt SoC", color="teal", linewidth=2.5)
plt.axvline(4.05, color="#0f766e", linestyle=":", alpha=0.8, label="ETA4054 rest-full (~4.05 V)")
plt.axvline(3.26, color="#b91c1c", linestyle=":", alpha=0.8, label="Empty cliff (~3.26 V)")
plt.title("Voltage vs. Battery Percentage")
plt.xlabel("Voltage (V)")
plt.ylabel("Percentage (%)")
plt.grid(True, linestyle="--", alpha=0.6)
plt.xlim(3.25, 4.25)
plt.ylim(-5, 105)
plt.axhline(0, color="red", linestyle=":", alpha=0.7)
plt.axhline(100, color="green", linestyle=":", alpha=0.7)
plt.legend()
plt.show()
