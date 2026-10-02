import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s]: %(message)s:')


project_name="mockbank"

list_of_files=[
    ".github/workflows/.gitkeep",
    f"app/{project_name}/__init__.py",
    f"app/{project_name}/core/__init__.py",
    f"app/{project_name}/core/config.py",
    f"app/{project_name}/api/__init__.py",
    f"app/{project_name}/api/routes/__init__.py",
    f"app/{project_name}/api/routes/auth.py",
    f"app/{project_name}/api/routes/accounts.py",
    f"app/{project_name}/api/routes/payments.py",
    f"app/{project_name}/api/routes/webhooks.py",
    f"app/{project_name}/models/__init__.py",
    f"app/{project_name}/models/schemas.py",
    f"app/{project_name}/services/__init__.py",
    f"app/{project_name}/services/accounts.py",
    f"app/{project_name}/services/payments.py",
    f"app/{project_name}/db/__init__.py",
    f"app/{project_name}/db/store.py",
    f"app/{project_name}/utils/__init__.py",
    f"app/{project_name}/utils/common.py",
    "tests/__init__.py",
    "tests/test_accounts.py",
    "tests/test_payments.py",
    "data/.keep",
    "main.py",
    "Dockerfile",
    "requirements.txt",
    ".env",
    ".env.example",
    ".gitignore",

]

for filepath in list_of_files:
    filepath = Path(filepath)
    filedir, filename = os.path.split(filepath)

    if filedir != "":
        os.makedirs(filedir, exist_ok=True)
        logging.info(f"Creating directory:{filedir} for the file {filename}")

    
    if (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0):
        with open(filepath,'w') as f:
            pass
            logging.info(f"Creating empty file: {filepath}")


    
    else:
        logging.info(f"{filename}  already exists")