import matplotlib.pyplot as plt
import numpy as np

# Generate voltages from 3.30V to 4.20V
volts = np.linspace(3.30, 4.20, 100)
pct = (volts - 3.30) * 100.0 / (4.20 - 3.30)

# Create the plot
plt.figure(figsize=(8, 5))
plt.plot(volts, pct, label="Linear Battery Approximation", color="teal", linewidth=2.5)
plt.title("Voltage vs. Battery Percentage")
plt.xlabel("Voltage (V)")
plt.ylabel("Percentage (%)")
plt.grid(True, linestyle="--", alpha=0.6)
plt.xlim(3.25, 4.25)
plt.ylim(-5, 105)
plt.axhline(0, color='red', linestyle=':', alpha=0.7)
plt.axhline(100, color='green', linestyle=':', alpha=0.7)
plt.legend()
plt.show()
