from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import pandas as pd
import numpy as np
import os
import time
import logging

# Configuración básica de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === IA LIGERA: función de detección dinámica de título ===
def infer_dominant_text(elements, top_n=1):
    texts = [e.text.strip() for e in elements if e.text.strip()]
    if not texts:
        return []
    
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(texts)
    kmeans = KMeans(n_clusters=min(top_n, len(texts)), n_init="auto")
    kmeans.fit(X)
    centroids = kmeans.cluster_centers_
    scores = kmeans.transform(X).mean(axis=1)
    
    sorted_indices = np.argsort(scores)[:top_n]
    return [texts[i] for i in sorted_indices]

# === INICIO DEL PROCESO ===
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

    # Configurar navegador en modo headless
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get("https://www.yogonet.com/international/")
    time.sleep(3)

    # Scroll automático
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
    containers = driver.find_elements(By.XPATH, "//div[.//a and (.//h2 or .//h3 or .//p or .//span)]")

    for container in containers:
        try:
            text_elements = container.find_elements(By.XPATH, ".//*[(self::h1 or self::h2 or self::h3 or self::p or self::span) and string-length(normalize-space()) > 0]")
            title_candidates = infer_dominant_text(text_elements)
            title = title_candidates[0] if title_candidates else ""

            if title in titles or not title:
                continue
            titles.append(title)

            kicker = next((e.text.strip() for e in text_elements if e.text.strip() and e.text.strip() != title and len(e.text.strip()) < 80), "")

            image_url = ""
            try:
                img_tag = container.find_element(By.XPATH, ".//img")
                image_url = img_tag.get_attribute("src")
            except:
                pass

            link = ""
            try:
                link_tag = container.find_element(By.XPATH, ".//a")
                link = link_tag.get_attribute("href")
            except:
                pass

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

    # Crear DataFrame y enriquecer
    df = pd.DataFrame(results)
    df["word_count"] = df["title"].apply(lambda x: len(x.split()))
    df["char_count"] = df["title"].apply(lambda x: len(x))
    df["capitalized_words"] = df["title"].apply(lambda x: [w for w in x.split() if w.istitle()])

    # Subir a BigQuery
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    job_config = bigquery.LoadJobConfig(autodetect=True)
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    logging.info("✅ El scraping y la carga a BigQuery finalizaron correctamente.")

except Exception as e:
    logging.error(f"❌ Error inesperado: {e}")