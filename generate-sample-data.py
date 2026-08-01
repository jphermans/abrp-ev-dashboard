#!/usr/bin/env python3
"""
Generate a sample ABRP-format Excel file with fake EV driving data.
Run: python3 generate-sample-data.py
Output: sample-data/sample-export.xlsx
"""

import random
from datetime import datetime, timedelta

try:
    import openpyxl
except ImportError:
    print("Installing openpyxl...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

def generate():
    random.seed(42)
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ABRP Activities"
    
    # Headers (matching ABRP export format)
    headers = [
        "Activiteit", "Starttijd", "Eindtijd", "Duur", "Afstand [mi]",
        "Beginlocatie", "Eindlocatie", "Start SoC", "Eind SoC",
        "Energie bijgeladen [kWh]", "Start kilometertester [mi]",
        "Eind kilometerteller [mi]", "Voertuig"
    ]
    
    # Title rows
    ws.append(["ABRP Activities — Sample Data"])
    ws.append([])
    ws.append(headers)
    
    odo = 10000.0
    current = datetime(2026, 5, 1)
    end = datetime(2026, 7, 31)
    
    providers = [
        ("DATS 24", 30), ("Fastned", 20), ("Allego", 20),
        ("Shell Recharge", 10), ("Ionity", 5), (None, 15)
    ]
    
    while current <= end:
        if random.random() < 0.25:
            current += timedelta(days=1)
            continue
        
        n_trips = random.choice([1, 1, 2, 2, 3])
        
        for _ in range(n_trips):
            if random.random() < 0.15:
                dist_km = random.choice([95, 130, 150, 180, 220])
            else:
                dist_km = random.choice([20, 38, 42, 65, 96, 155])
            
            dist_mi = round(dist_km / 1.609344)
            odo_end = odo + dist_mi
            
            hour = random.choice([5, 6, 7, 8, 13, 14, 15, 16, 17])
            dt = current.replace(hour=hour, minute=random.randint(0, 59))
            
            soc_start = random.randint(30, 80)
            soc_end = max(15, soc_start - int(dist_km * 0.18))
            
            ws.append([
                "Rijd",
                dt.strftime("%m/%d/%Y %H:%M"),
                (dt + timedelta(minutes=int(dist_km))).strftime("%m/%d/%Y %H:%M"),
                f"{dist_km // 60} u {int((dist_km % 60) / 60 * 60)} min" if dist_km > 60 else f"{int(dist_km)} min",
                dist_mi,
                f"50.94, 4.05\n(Start Location)",
                f"51.40, 5.40\n(End Location)",
                soc_start / 100,
                soc_end / 100,
                None,
                odo,
                odo_end,
                "Your EV"
            ])
            odo = odo_end
        
        if random.random() < 0.55:
            provider = random.choices(
                [p[0] for p in providers],
                weights=[p[1] for p in providers]
            )[0]
            
            energy = round(random.uniform(7, 45), 1)
            soc_start = random.randint(15, 40)
            soc_end = min(85, soc_start + int(energy * 1.5))
            
            charge_dt = current.replace(
                hour=random.randint(10, 18),
                minute=random.randint(0, 59)
            )
            
            loc_name = f"({provider})" if provider else "(Public Charger)"
            
            ws.append([
                "Laad op",
                charge_dt.strftime("%m/%d/%Y %H:%M"),
                (charge_dt + timedelta(minutes=random.randint(5, 22))).strftime("%m/%d/%Y %H:%M"),
                f"{random.randint(5, 22)} min",
                None,
                f"51.04, 3.78\n{loc_name}",
                f"51.04, 3.78\n{loc_name}",
                soc_start / 100,
                soc_end / 100,
                energy,
                odo,
                odo,
                "Your EV"
            ])
        
        current += timedelta(days=1)
    
    import os
    os.makedirs("sample-data", exist_ok=True)
    wb.save("sample-data/sample-export.xlsx")
    print(f"✅ Generated sample-export.xlsx with {ws.max_row - 3} records")

if __name__ == "__main__":
    generate()
