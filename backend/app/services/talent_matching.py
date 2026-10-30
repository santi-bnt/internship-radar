"""Company/context matching; no candidate or project names participate in ranking."""
import json
import re

AREA_SIGNALS = {
    "Robotics": ["robot", "robotic", "robotics", "actuator", "motor", "servo", "integration"],
    "Embedded Systems": ["embedded", "firmware", "freertos", "rtos", "microcontroller", "uart", "interrupt", "real-time", "mutex", "semaphore", "queue"],
    "Software Engineering": ["software", "python", "api", "backend", "fastapi", "postgresql", "typescript", "testing"],
    "Controls": ["control", "controls", "motor", "pwm", "servo", "timing"],
    "Autonomous Systems": ["robotics", "sensor", "autonomous", "real-time", "embedded"],
    "FPGA / Digital Systems": ["fpga", "verilog", "digital", "testbench", "waveform"],
    "Hardware Software Integration": ["hardware", "integration", "uart", "gpio", "kl25z", "esp32", "raspberry pi"],
}


def score_talent_project(project, context):
    try:
        data = json.loads(context)
    except (ValueError, TypeError):
        data = {"company_areas": [], "targets": [area for area in AREA_SIGNALS if area.lower() in context.lower()], "description": context}
    text = json.dumps(project, ensure_ascii=False).lower()
    score = 0.0
    # Description terms influence ranking without turning them into requirements.
    description = data.get("description", "").lower()
    score += min(8, sum(1 for word in set(re.findall(r"[a-z]{5,}", description)) if word in text))
    if "Embedded Systems" in data["targets"]:
        # Real-time synchronization is deep embedded evidence distinct from GPIO use.
        score += 3 * sum(term in text for term in ("freertos", "mutex", "semaphore", "queue", "interrupt"))
    for areas, weight in ((data["company_areas"], 1.0), (data["targets"], 3.0)):
        for area in dict.fromkeys(areas):
            signals = AREA_SIGNALS.get(area, [area.lower()])
            hits = sum(bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)) for term in signals)
            score += weight * min(hits, 6)
    # Smooth normalization preserves distinctions even for rich robotics projects.
    return round(100 * score / (score + 25), 2)
