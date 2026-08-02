import matplotlib.pyplot as plt
import numpy as np

# Piecewise LiPo OCV curve (matches battery::estimatePercent).
OCV = np.array(
    [
        [4.20, 100],
        [4.15, 95],
        [4.11, 90],
        [4.08, 85],
        [4.02, 80],
        [3.98, 75],
        [3.95, 70],
        [3.91, 65],
        [3.87, 60],
        [3.85, 55],
        [3.84, 50],
        [3.82, 45],
        [3.80, 40],
        [3.79, 35],
        [3.77, 30],
        [3.75, 25],
        [3.73, 20],
        [3.71, 15],
        [3.69, 10],
        [3.61, 5],
        [3.30, 0],
    ]
)

volts = np.linspace(3.30, 4.20, 200)
legacy = (volts - 3.30) * 100.0 / (4.20 - 3.30)
ocv_pct = np.interp(volts, OCV[::-1, 0], OCV[::-1, 1])

plt.figure(figsize=(8, 5))
plt.plot(volts, legacy, label="Legacy linear 3.30–4.20", color="#6b7280", linestyle="--", linewidth=1.8)
plt.plot(volts, ocv_pct, label="LiPo resting OCV (firmware)", color="teal", linewidth=2.5)
plt.axvline(3.63, color="#b45309", linestyle=":", alpha=0.8, label="USB charge start (~3.63 V)")
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
