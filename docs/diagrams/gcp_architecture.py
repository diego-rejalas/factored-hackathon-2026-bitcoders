"""GCP prod architecture. Run: python gcp_architecture.py  (needs `pip install diagrams` and Graphviz)."""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.storage import S3
from diagrams.gcp.compute import ComputeEngine, Run
from diagrams.gcp.database import SQL
from diagrams.gcp.devtools import ContainerRegistry
from diagrams.gcp.network import NAT, VPC, Armor, LoadBalancing
from diagrams.gcp.operations import Logging, Monitoring
from diagrams.gcp.security import IAP, Iam, SecretManager
from diagrams.gcp.storage import GCS
from diagrams.generic.compute import Rack
from diagrams.onprem.client import User, Users
from diagrams.onprem.vcs import Github

graph_attr = {
    "fontsize": "22",
    "fontname": "Helvetica-Bold",
    "labelloc": "t",
    "pad": "0.5",
    "nodesep": "0.5",
    "ranksep": "0.9",
    "splines": "spline",
    "compound": "true",
}
cluster_attr = {"fontname": "Helvetica-Bold", "fontsize": "14", "labeljust": "l", "margin": "20"}
edge_attr = {"fontname": "Helvetica", "fontsize": "11", "color": "#5F6368", "fontcolor": "#3C4043"}

with Diagram(
    "Arquitectura de referencia en Google Cloud (prod)",
    filename="gcp-architecture",
    outformat=["png", "svg"],
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    edge_attr=edge_attr,
):
    cliente = Users("Cliente\n(navegador)")
    operador = User("Operador\n(datos)")
    gha = Github("GitHub Actions\nCI/CD")
    s3 = S3("S3 del organizador\n(us-east-2)")
    llm = Rack("OpenRouter\n(LLM)")

    with Cluster("Google Cloud", graph_attr={**cluster_attr, "bgcolor": "#FFFFFF", "pencolor": "#4285F4"}):
        with Cluster("Entrada (global)", graph_attr={**cluster_attr, "bgcolor": "#FDF3E3", "pencolor": "#F9AB00"}):
            armor = Armor("14  Cloud Armor\nWAF y límite por IP")
            lb = LoadBalancing("15  ALB global\nHTTPS, certificado gestionado")
        with Cluster("Región us-east4", graph_attr={**cluster_attr, "bgcolor": "#F1F6FE", "pencolor": "#4285F4", "style": "dashed"}):

            with Cluster("Servicios regionales", graph_attr={**cluster_attr, "bgcolor": "#F8F9FA", "pencolor": "#9AA0A6"}):
                registry = ContainerRegistry("1  Artifact Registry\nimágenes por commit")
                secrets = SecretManager("2  Secret Manager\nclaves y contraseñas")
                lake = GCS("3  Cloud Storage\nlakehouse")
                logs = Logging("4  Cloud Logging")
                mon = Monitoring("4  Cloud Monitoring\nmétricas por defecto,\nsin alertas")
                iam = Iam("5  IAM\ncuenta por servicio")

            with Cluster("VPC  factored-prod", graph_attr={**cluster_attr, "bgcolor": "#E9F5EC", "pencolor": "#34A853"}):
                iap = IAP("6  Cloud IAP + OS Login\nsin IP pública")

                with Cluster("Subred de aplicación  10.30.0.0/24", graph_attr={**cluster_attr, "bgcolor": "#F6FBF7", "pencolor": "#34A853", "style": "dashed"}):
                    with Cluster("Cloud Run  (Direct VPC egress)", graph_attr={**cluster_attr, "bgcolor": "#FFFFFF", "pencolor": "#4285F4"}):
                        frontend = Run("7  frontend\nNext.js")
                        agent = Run("8  agent\nLangGraph")
                        backend = Run("9  backend\nFastAPI, solo lectura")
                        etl = Run("10  Job etl\na demanda")
                    with Cluster("VM de orquestación", graph_attr={**cluster_attr, "bgcolor": "#FFFFFF", "pencolor": "#FBBC04"}):
                        airflow = ComputeEngine("11  Airflow 3 + dbt\ne2-standard-4\napagada 03:00")
                    nat = NAT("12  Cloud NAT\nsalida de la VM")

                with Cluster("Servicios privados  10.30.1.0/24  (Private Service Access)", graph_attr={**cluster_attr, "bgcolor": "#FDECEA", "pencolor": "#EA4335", "style": "dashed"}):
                    sql = SQL("13  Cloud SQL\nPostgreSQL 18\nIP privada, SSL")

    cliente >> Edge(label="HTTPS", color="#1A73E8", penwidth="2") >> armor >> lb
    lb >> Edge(label="/", color="#1A73E8") >> frontend
    lb >> Edge(label="/agent/*", color="#1A73E8") >> agent
    agent >> Edge(label="herramientas HTTP\nID token (solo su cuenta)") >> backend
    backend >> Edge(label="backend_app: solo lee gold") >> sql
    agent >> Edge(label="razonamiento") >> llm

    operador >> Edge(label="túnel TCP 8080") >> iap >> airflow
    s3 >> Edge(label="extract") >> nat >> airflow
    airflow >> Edge(label="Parquet") >> lake
    airflow >> Edge(label="publish_gold", color="#EA4335", penwidth="2") >> sql
    etl >> Edge(label="alternativa", style="dashed") >> sql

    gha >> Edge(label="build y push") >> registry
    registry >> Edge(label="imagen", style="dashed") >> airflow
    secrets >> Edge(label="secretos", style="dashed") >> agent
    airflow >> Edge(label="registros", style="dotted", color="#9AA0A6") >> logs
    logs - Edge(style="invis") - mon
    iam - Edge(style="invis") - secrets


# The library writes absolute paths to its icon files into the SVG, which break anywhere but this machine
# (GitHub shows no icons). Embed them so the SVG is self-contained.
import base64
import pathlib
import re

_svg = pathlib.Path("gcp-architecture.svg")
_svg.write_text(re.sub(
    r'xlink:href="([^"]+\.png)"',
    lambda m: 'xlink:href="data:image/png;base64,' + base64.b64encode(pathlib.Path(m.group(1)).read_bytes()).decode() + '"',
    _svg.read_text(),
))
