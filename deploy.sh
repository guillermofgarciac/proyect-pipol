#!/bin/bash

# === Configuración ===
PROJECT_ID="pipol-proyect"
REGION="us-central1"
SERVICE_NAME="pipol-scraper"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

# === Build de imagen Docker ===
echo "🔧 Construyendo imagen Docker..."
docker build -t $IMAGE_NAME .

# === Autenticación de Docker con GCR ===
echo "🔐 Autenticando Docker con Container Registry..."
gcloud auth configure-docker

# === Push de imagen a GCR ===
echo "📦 Subiendo imagen a Google Container Registry..."
docker push $IMAGE_NAME

# === Crear o actualizar Job en Cloud Run ===
echo "🚀 Configurando Cloud Run Job..."
EXISTS=$(gcloud beta run jobs list --region=$REGION --format="value(name)" | grep -w "$SERVICE_NAME")

if [ -n "$EXISTS" ]; then
  echo "🔁 Actualizando Job existente..."
  gcloud beta run jobs update $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --memory 512Mi \
    --task-timeout=600s \
    --command "python" \
    --args "scraper.py"
else
  echo "🆕 Creando nuevo Job..."
  gcloud beta run jobs create $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --memory 512Mi \
    --task-timeout=600s \
    --command "python" \
    --args "scraper.py"
fi

# === Ejecutar el Job ===
echo "🚀 Ejecutando el Job en Cloud Run..."
gcloud beta run jobs execute $SERVICE_NAME --region $REGION

echo "✅ Job ejecutado exitosamente."
