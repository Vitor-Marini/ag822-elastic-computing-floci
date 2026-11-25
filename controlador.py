"""Controlador de escala do AgendaSaude RP.
Ouve os alarmes (CloudWatch -> SNS -> SQS), ajusta a capacidade do ASG e aplica
as acoes agendadas da Etapa 4 no relogio simulado escrito pelo gerador."""
import argparse, json, time
from datetime import datetime, timedelta, timezone
import boto3

ASG = "agenda-web-asg"
FILA = "agenda-escala-eventos"
ALVO = 105        # req/min por instancia que queremos manter
COOLDOWN = 60     # segundos reais entre duas acoes dinamicas
# Escala por etapas: (excesso relativo ao ALVO, instancias a acrescentar)
ETAPAS = [(0.5, 1), (1.0, 2), (float("inf"), 3)]

p = argparse.ArgumentParser()
p.add_argument("--sem-agendadas", action="store_true", help="ignora as acoes agendadas")
args = p.parse_args()

asg = boto3.client("autoscaling")
cw = boto3.client("cloudwatch")
sqs = boto3.client("sqs")
fila_url = sqs.get_queue_url(QueueName=FILA)["QueueUrl"]
ultima_acao, aplicadas = 0.0, set()


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def hora_simulada():
    try:
        with open("relogio.json") as r:
            return json.load(r)["hora"]
    except (OSError, ValueError):
        return None


def aplicar_agendadas(agora):
    acoes = asg.describe_scheduled_actions(AutoScalingGroupName=ASG)["ScheduledUpdateGroupActions"]
    pendentes = []
    for a in acoes:
        if not a.get("Recurrence"):
            continue
        minuto, hora = a["Recurrence"].split()[:2]
        pendentes.append((int(hora) + int(minuto) / 60, a))
    for quando, a in sorted(pendentes, key=lambda x: x[0]):
        nome = a["ScheduledActionName"]
        if quando <= agora and nome not in aplicadas:
            params = {k: a[k] for k in ("MinSize", "MaxSize", "DesiredCapacity") if k in a}
            asg.update_auto_scaling_group(AutoScalingGroupName=ASG, **params)
            aplicadas.add(nome)
            log(f"[agendada] {nome} -> {params}")


def metrica_recente():
    fim = datetime.now(timezone.utc)
    r = cw.get_metric_statistics(
        Namespace="AgendaSaude/Portal", MetricName="RequisicoesPorInstancia",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": ASG}],
        StartTime=fim - timedelta(seconds=120), EndTime=fim, Period=60, Statistics=["Average"])
    pontos = r["Datapoints"]
    return max(pontos, key=lambda d: d["Timestamp"])["Average"] if pontos else None


def estado(alarmes, nome):
    return alarmes.get(nome, {}).get("StateValue")


log("controlador iniciado")
while True:
    # 1) Eventos: notificacoes que os alarmes publicaram no SNS e chegaram na fila
    resp = sqs.receive_message(QueueUrl=fila_url, MaxNumberOfMessages=10, WaitTimeSeconds=5)
    for m in resp.get("Messages", []):
        try:
            alarme = json.loads(json.loads(m["Body"])["Message"])
            log(f"[evento] {alarme['AlarmName']}: {alarme['OldStateValue']} -> {alarme['NewStateValue']}")
        except (KeyError, ValueError, TypeError):
            log(f"[evento] mensagem nao reconhecida: {m['Body'][:120]}")
        sqs.delete_message(QueueUrl=fila_url, ReceiptHandle=m["ReceiptHandle"])

    # 2) Acoes agendadas no relogio simulado
    agora = hora_simulada()
    if agora is not None and not args.sem_agendadas:
        aplicar_agendadas(agora)

    # 3) Decisao dinamica: enquanto um alarme estiver em ALARM, age a cada COOLDOWN
    if time.time() - ultima_acao < COOLDOWN:
        continue
    alarmes = {a["AlarmName"]: a for a in cw.describe_alarms(
        AlarmNames=["agenda-demanda-alta", "agenda-demanda-baixa"])["MetricAlarms"]}
    g = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG])["AutoScalingGroups"][0]
    atual, novo = g["DesiredCapacity"], g["DesiredCapacity"]
    if estado(alarmes, "agenda-demanda-alta") == "ALARM":
        valor = metrica_recente() or ALVO
        excesso = valor / ALVO - 1
        soma = next(n for limite, n in ETAPAS if excesso < limite)
        novo = min(g["MaxSize"], atual + soma)
        motivo = f"{valor:.0f} req/inst ({excesso:+.0%} do alvo)"
    elif estado(alarmes, "agenda-demanda-baixa") == "ALARM":
        novo = max(g["MinSize"], atual - 1)
        motivo = "demanda baixa"
    if novo != atual:
        asg.set_desired_capacity(AutoScalingGroupName=ASG, DesiredCapacity=novo, HonorCooldown=False)
        ultima_acao = time.time()
        log(f"[dinamica] desejada {atual} -> {novo} ({motivo})")
