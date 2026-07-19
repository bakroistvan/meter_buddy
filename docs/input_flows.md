# Meter Buddy - Input Flows & Behavior

This document visually maps how the ESP32-C3 firmware responds to external hardware and software inputs. Since the device operates almost entirely in deep sleep to conserve battery, its behavior is strictly event-driven based on specific wakeup causes.

## 1. Pulse Sensor Flow (GPIO4)
When the TEMT6000 light sensor detects a flash from the utility meter, it sends a rising edge to GPIO4. To maximize flash memory life, this flow intentionally avoids writing to LittleFS, storing the state purely in RTC RAM (`RTC_DATA_ATTR`).

```mermaid
flowchart TD
    Sleep((Deep Sleep)) -->|Pulse Wake Pin RISING| Wake[ESP32 Wakes Up]
    Wake --> Debounce[Debounce Signal]
    Debounce --> CheckSpeed{Frequent Pulses?}
    
    CheckSpeed -->|Yes| StayAwake[Stay Awake]
    StayAwake --> CountInterrupts[Count Pulses via Hardware Interrupt]
    CountInterrupts --> Quiet{Is Sensor Quiet?}
    Quiet -->|No| CountInterrupts
    Quiet -->|Yes| Inc
    
    CheckSpeed -->|No| Inc
    
    Inc[Increment `rtcCurrentPulses` in RTC RAM] --> GoSleep((Return to Deep Sleep))
    
    style Sleep fill:#1f2937,stroke:#374151,color:#fff
    style Wake fill:#3b82f6,stroke:#2563eb,color:#fff
    style GoSleep fill:#1f2937,stroke:#374151,color:#fff
```

---

## 2. RTC Alarm Flow (GPIO5)
The DS3231 RTC triggers an alarm every 60 seconds. This acts as the device's "heartbeat" to commit the hot pulse counts into permanent cold storage (LittleFS).

```mermaid
flowchart TD
    Sleep((Deep Sleep)) -->|RTC Wake Pin LOW| Wake[ESP32 Wakes Up]
    Wake --> ClearAlarm[Clear DS3231 Interrupt Flag]
    ClearAlarm --> ReadBatt[Sample Battery Voltage via ADC]
    ReadBatt --> Roll[Package Current Period]
    
    Roll --> Save[Append to `/records.bin` on LittleFS]
    Save --> Reset[Reset `rtcCurrentPulses` to 0]
    Reset --> Schedule[Schedule Next RTC Alarm in 60s]
    Schedule --> GoSleep((Return to Deep Sleep))

    style Sleep fill:#1f2937,stroke:#374151,color:#fff
    style Wake fill:#10b981,stroke:#059669,color:#fff
    style Save fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style GoSleep fill:#1f2937,stroke:#374151,color:#fff
```

---

## 3. Upload Button Flow (GPIO3)
A user short-press initiates the network upload cycle. This sequence orchestrates Wi-Fi connection, time synchronization, data payload POSTing, and checking for Over-The-Air (OTA) firmware updates.

```mermaid
flowchart TD
    Sleep((Deep Sleep)) -->|Button Pin LOW| Wake[ESP32 Wakes Up]
    Wake --> PreRoll[Roll pending pulses to LittleFS]
    PreRoll --> LoadBatch[Load max 48 unacknowledged records]
    LoadBatch --> Wifi[Connect to Wi-Fi]
    
    Wifi -->|Failed| GoSleep((Return to Deep Sleep))
    Wifi --> |Connected| NTP[Sync Time via NTP]
    NTP --> HttpPost[POST payload to Backend]
    
    HttpPost -->|HTTP 200/201| Sync[Update `/sync.dat` sync pointer]
    Sync --> Compact[Compact `/records.bin` to reclaim space]
    Compact --> CheckFirmware
    
    HttpPost -->|Error / Reject| SkipSync[Keep records for next upload attempt]
    SkipSync --> CheckFirmware
    
    CheckFirmware[Check /firmware/version via HTTPUpdate]
    
    CheckFirmware -->|New Version Available| OTA[Download .bin and Flash to OTA Slot]
    OTA --> Reboot((Hardware Reboot))
    CheckFirmware -->|No Update / Error| GoSleep
    
    style Sleep fill:#1f2937,stroke:#374151,color:#fff
    style Wake fill:#f59e0b,stroke:#d97706,color:#fff
    style HttpPost fill:#ef4444,stroke:#dc2626,color:#fff
    style OTA fill:#ec4899,stroke:#db2777,color:#fff
    style GoSleep fill:#1f2937,stroke:#374151,color:#fff
    style Reboot fill:#1f2937,stroke:#374151,color:#fff
```

---

## 4. Diagnostic Boot Flow (USB/Reset)
When the device is powered on, manually reset via the button, or wakes up from an undefined source (not a GPIO interrupt), it drops into a debugging shell instead of going to sleep.

```mermaid
flowchart TD
    Reset((Power-On / Manual Reset)) --> Boot[ESP32 Boots]
    Boot --> Reason{Wakeup Reason?}
    
    Reason -->|GPIO Trigger| NormalFlow[Follow normal Sleep/Wake Flows]
    Reason -->|Not GPIO| DiagMode[Enter Diagnostic Mode]
    
    DiagMode --> Print[Print battery & storage pointer status]
    Print --> Loop[Start Serial REPL Loop]
    Loop --> WaitCmd[Wait for Serial Command on USB]
    
    WaitCmd -->|'dump'| Dump[Print LittleFS Sync State]
    WaitCmd -->|'status'| Stat[Print Battery & WiFi Status]
    WaitCmd -->|'clear'| Clear[Delete all LittleFS files]
    WaitCmd -->|'reboot'| Re((ESP.restart))
    
    Dump --> Loop
    Stat --> Loop
    Clear --> Loop
    
    style Reset fill:#1f2937,stroke:#374151,color:#fff
    style DiagMode fill:#6366f1,stroke:#4f46e5,color:#fff
    style Re fill:#1f2937,stroke:#374151,color:#fff
```
