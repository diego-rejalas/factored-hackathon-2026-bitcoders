#!/usr/bin/env bash
# ==============================================================================
# Script de Aprovisionamiento de Accesos de Equipo para GCP y Cloud SQL
# Bitcoders - Factored AI & Data Hackathon 2026
#
# Uso:
#   ./infra/gcp/scripts/grant_access.sh correo1@gmail.com correo2@gmail.com
# O interactivo:
#   ./infra/gcp/scripts/grant_access.sh
# ==============================================================================

set -euo pipefail

# Colores para salida de terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT="${GCP_PROJECT_ID:-bitcoders-factored-hackathon}"
# Environment of the stack (dev, qa or prod). INSTANCE and REGION can be overridden, for example
# INSTANCE=factored-hackathon REGION=us-central1 for the stack deployed before the environment split.
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-factored-${ENVIRONMENT}}"
REGION="${REGION:-us-east4}"
CREDENTIALS_FILE="team_credentials.txt"

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}  Aprovisionamiento de Accesos de Equipo - GCP & Cloud SQL       ${NC}"
echo -e "${BLUE}  Proyecto: ${YELLOW}${PROJECT}${BLUE} | Instancia: ${YELLOW}${INSTANCE}${NC}"
echo -e "${BLUE}================================================================${NC}\n"

# Obtener lista de correos
EMAILS=("$@")
if [ ${#EMAILS[@]} -eq 0 ]; then
    echo -e "${YELLOW}Ingresa los correos de los miembros del equipo (separados por espacio):${NC}"
    read -r -a EMAILS
fi

if [ ${#EMAILS[@]} -eq 0 ]; then
    echo -e "${RED}Error: No se proporcionó ningún correo. Operación cancelada.${NC}"
    exit 1
fi

# Inicializar o limpiar archivo de credenciales local
echo "# =========================================================" > "$CREDENTIALS_FILE"
echo "# Credenciales de Acceso al Equipo - $(date)" >> "$CREDENTIALS_FILE"
echo "# PROYECTO GCP: $PROJECT" >> "$CREDENTIALS_FILE"
echo "# INSTANCIA CLOUD SQL: $INSTANCE (Region: $REGION)" >> "$CREDENTIALS_FILE"
echo "# BASE DE DATOS: data" >> "$CREDENTIALS_FILE"
echo "# =========================================================" >> "$CREDENTIALS_FILE"
echo "" >> "$CREDENTIALS_FILE"

# Verificar estado de Cloud SQL antes de crear usuarios
echo -e "${BLUE}▶ Verificando estado de Cloud SQL ($INSTANCE)...${NC}"
DB_STATE=$(gcloud sql instances describe "$INSTANCE" --project="$PROJECT" --format="value(state)" 2>/dev/null || echo "UNKNOWN")
DB_POLICY=$(gcloud sql instances describe "$INSTANCE" --project="$PROJECT" --format="value(settings.activationPolicy)" 2>/dev/null || echo "UNKNOWN")

if [ "$DB_STATE" = "STOPPED" ] || [ "$DB_POLICY" = "NEVER" ]; then
    echo -e "${YELLOW}⚠ La instancia está hibernada ($DB_STATE / $DB_POLICY). Reanudando para crear usuarios...${NC}"
    gcloud sql instances patch "$INSTANCE" --project="$PROJECT" --activation-policy=ALWAYS --quiet
    echo -e "${GREEN}✔ Instancia reanudada exitosamente.${NC}"
fi

for EMAIL in "${EMAILS[@]}"; do
    # Limpiar espacios
    EMAIL=$(echo "$EMAIL" | tr -d '[:space:]')
    [ -z "$EMAIL" ] && continue

    echo -e "\n${BLUE}▶ Procesando acceso para: ${GREEN}${EMAIL}${NC}"

    # 1. Asignar rol de GCP IAM
    echo "  1. Asignando rol de Editor en el proyecto GCP ($PROJECT)..."
    if gcloud projects add-iam-policy-binding "$PROJECT" \
        --member="user:${EMAIL}" \
        --role="roles/editor" \
        --quiet > /dev/null 2>&1; then
        echo -e "     ${GREEN}✔ Rol IAM 'roles/editor' asignado exitosamente.${NC}"
    else
        echo -e "     ${RED}✖ Error al asignar rol IAM. Verifica tus permisos de Administrador en el proyecto.${NC}"
    fi

    # 2. Generar nombre de usuario PostgreSQL a partir del correo
    DB_USER=$(echo "$EMAIL" | cut -d'@' -f1 | tr '.-' '_' | tr '[:upper:]' '[:lower:]')
    # Generar contraseña segura aleatoria de 16 caracteres
    DB_PASSWORD=$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9!@#%^&*' | head -c 16)

    # 3. Crear usuario en Cloud SQL PostgreSQL
    echo "  2. Creando usuario PostgreSQL en Cloud SQL ('${DB_USER}')..."
    if gcloud sql users describe "$DB_USER" --instance="$INSTANCE" --project="$PROJECT" > /dev/null 2>&1; then
        echo -e "     ${YELLOW}⚠ El usuario '$DB_USER' ya existía. Actualizando contraseña...${NC}"
        gcloud sql users set-password "$DB_USER" \
            --instance="$INSTANCE" \
            --project="$PROJECT" \
            --password="$DB_PASSWORD" \
            --quiet
    else
        gcloud sql users create "$DB_USER" \
            --instance="$INSTANCE" \
            --project="$PROJECT" \
            --password="$DB_PASSWORD" \
            --quiet
    fi
    echo -e "     ${GREEN}✔ Usuario de base de datos listo.${NC}"

    # 4. Registrar en archivo de credenciales
    cat <<EOF >> "$CREDENTIALS_FILE"
---------------------------------------------------------
MIEMBRO: $EMAIL
---------------------------------------------------------
- Google Cloud Project: $PROJECT
- Cloud SQL Instance:   $INSTANCE ($REGION)
- Host (Local Proxy):   127.0.0.1 (o localhost)
- Puerto:               5432
- Base de datos:        data
- Usuario PostgreSQL:   $DB_USER
- Contraseña:           $DB_PASSWORD

Instrucciones rápidas para el usuario:
  1. gcloud auth login
  2. gcloud config set project $PROJECT
  3. ./cloud-sql-proxy $PROJECT:$REGION:$INSTANCE
  4. Conectar cliente (DBeaver, psql) a localhost:5432/data con sus credenciales.
---------------------------------------------------------

EOF

done

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}  ✔ Todos los accesos fueron aprovisionados exitosamente!        ${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "Las credenciales y detalles individuales se guardaron en:"
echo -e "👉 ${YELLOW}${CREDENTIALS_FILE}${NC} (Este archivo está en .gitignore para seguridad)."
echo -e "\nPuedes compartir con tu equipo la guía de conexión en:"
echo -e "👉 ${BLUE}docs/ONBOARDING.md${NC}\n"
