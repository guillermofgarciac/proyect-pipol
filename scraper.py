from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


try:
    SCOPES = ['https://www.googleapis.com/auth/cloud-platform']
    CLIENT_SECRET_FILE = 'client_secret.json'
    TOKEN_FILE = 'application_default_credentials.json'

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    project_id = "pipol-proyect"
    client = bigquery.Client(credentials=creds, project=project_id)

    dataset_id = "pipol_dataset"
    table_id = "pipol_scraping_table_data"

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get("https://www.yogonet.com/international/")
    time.sleep(3)

    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    logging.info("✅ Scroll completo. Extrayendo noticias...")

    titles = []
    results = []
    containers = driver.find_elements(By.XPATH, "//div[.//a and (.//h2 or .//h3 or .//p)]")
    for container in containers:
        try:
            title = ""
            for tag in ["h2", "h3"]:
                elems = container.find_elements(By.TAG_NAME, tag)
                title = next((e.text.strip() for e in elems if e.text.strip()), "")
                if title:
                    break
            if title in titles:
                continue
            titles.append(str(title))

            kicker = ""
            spans = container.find_elements(By.TAG_NAME, "span")
            kicker = next((s.text.strip() for s in spans if len(s.text.strip()) > 0 and len(s.text.strip()) < 80), "")

            img_tag = container.find_element(By.TAG_NAME, "img")
            image_url = img_tag.get_attribute("src")

            link_tag = container.find_element(By.TAG_NAME, "a")
            link = link_tag.get_attribute("href")
            
            results.append({
                "title": title,
                "kicker": kicker,
                "image": image_url,
                "link": link
            })

        except Exception as e:
            logging.warning(f"⚠️ Error al procesar un contenedor: {e}")
            continue

    driver.quit()

    df = pd.DataFrame(results)
    df["word_count"] = df["title"].apply(lambda x: len(x.split()))
    df["char_count"] = df["title"].apply(lambda x: len(x))
    df["capitalized_words"] = df["title"].apply(lambda x: [w for w in x.split() if w.istitle()])

    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    job_config = bigquery.LoadJobConfig(autodetect=True)
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    logging.info("✅ El código terminó correctamente.")

except Exception as e:
    logging.error(f"❌ Error inesperado: {e}")