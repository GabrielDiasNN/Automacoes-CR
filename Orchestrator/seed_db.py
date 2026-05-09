import json
import os
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models

# Criar tabelas
models.Base.metadata.create_all(bind=engine)

def seed_database():
    db: Session = SessionLocal()
    
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    if not os.path.exists(config_path):
        print("config.json not found!")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    for task_info in config_data.get("tasks", []):
        task_name = task_info.get("name")
        if not task_name:
            continue
            
        # Verifica se ja existe
        existing = db.query(models.Automation).filter(models.Automation.name == task_name).first()
        schedule_str = str(task_info.get("schedule", ""))
        
        if not existing:
            new_auto = models.Automation(
                name=task_name,
                description=f"Importado do config.json",
                script_path=task_info.get("scriptPath", ""),
                schedule=schedule_str,
                enabled=task_info.get("enabled", True)
            )
            db.add(new_auto)
            print(f"Adicionada: {task_name}")
        else:
            # Atualiza
            existing.script_path = task_info.get("scriptPath", existing.script_path)
            existing.schedule = schedule_str
            existing.enabled = task_info.get("enabled", existing.enabled)
            print(f"Atualizada: {task_name}")

    db.commit()
    db.close()
    print("Seed completo!")

if __name__ == "__main__":
    seed_database()
