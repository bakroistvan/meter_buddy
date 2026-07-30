import asyncio
import math
import os
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# --- HOME ASSISTANT CONFIGURATION ---
HASS_URL = os.environ["HASS_URL"]
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
ENTITY_ID = os.environ["ENTITY_ID"]

# --- SIMULATION CONFIGURATION ---
TOTAL_DURATION_MIN = 20
SAMPLE_INTERVAL_SEC = 0.1  # Core physics loop speed (100ms)
PULSE_CONSTANT = 1000      # 1000 pulses per kWh (1 Wh per pulse)

# --- SINUSOIDAL LOAD CONFIGURATION ---
BASE_LOAD_KW = 1.0
AMPLITUDE_KW = 1.0


async def press_esphome_button(session: aiohttp.ClientSession, trigger_time: float):
    """
    Sends a stateless button.press command over the REST API.
    ESPHome reads this event and manages the 80ms hardware LED cycle out-of-band.
    """
    # Updated API endpoint specifically targeting the button domain
    url = f"{HASS_URL}/api/services/button/press"
    payload = {"entity_id": ENTITY_ID}

    try:
        # Out-of-band network transmission to keep calculation loop real-time
        async with session.post(url, json=payload, timeout=0.5) as resp:
            await resp.read()
            
        latency = time.time() - trigger_time
        print(f"🟢 [BUTTON PRESSED] Signal injected in {latency * 1000:.1f}ms. ESPHome handling hardware LED.")
    except Exception as e:
        print(f"❌ Network transmission error: {e}")


async def main():
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "content-type": "application/json",
    }

    energy_accumulator_wh = 0.0
    wh_threshold = 1000.0 / PULSE_CONSTANT
    pulse_count = 0

    total_seconds = TOTAL_DURATION_MIN * 60
    start_time = time.time()
    next_tick = start_time

    print(f"🚀 Async Integrator Running. Targeting Button Entity: {ENTITY_ID}")

    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            current_time = time.time()
            elapsed_sec = current_time - start_time

            #if elapsed_sec >= total_seconds:
            #    break

            # 1. Physics Engine: Calculate Sinusoidal Wave
            sine_angle = 2 * math.pi * (elapsed_sec / total_seconds)
            current_power_kw = max(0.0, BASE_LOAD_KW + AMPLITUDE_KW * math.sin(sine_angle))
            current_power_w = current_power_kw * 1000.0

            # 2. Integration Step (Power * Time slice in hours)
            hours_slice = SAMPLE_INTERVAL_SEC / 3600.0
            energy_slice_wh = current_power_w * hours_slice
            energy_accumulator_wh += energy_slice_wh

            # 3. Threshold Engine Check
            if energy_accumulator_wh >= wh_threshold:
                pulse_count += 1
                # Fire-and-forget: schedule the button press task instantly onto the event loop
                asyncio.create_task(press_esphome_button(session, time.time()))
                energy_accumulator_wh -= wh_threshold

            # Status printout inside the terminal every 2 seconds
            if int(elapsed_sec * 10) % 20 == 0:
                print(
                    f"⏱️ {elapsed_sec / 60:.2f}m/{TOTAL_DURATION_MIN}m | "
                    f"⚡ Load: {current_power_kw:.3f} kW | "
                    f"🔋 Accumulator: {energy_accumulator_wh:.4f} Wh | "
                    f"🔢 Total Pulses: {pulse_count}"
                )

            # 4. Phase Timing Sync (Prevents loop delay drift)
            next_tick += SAMPLE_INTERVAL_SEC
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    print(f"🏁 Simulation finished. Fired total button press pulses: {pulse_count}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Simulation terminated by user request.")