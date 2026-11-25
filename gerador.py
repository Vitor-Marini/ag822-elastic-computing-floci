"""Gerador de carga do AgendaSaude RP: simula um dia comprimido (1 h simulada = 60 s reais)."""
import argparse, collections, csv, json, math, time, urllib.request
import boto3

# Demanda média (req/min) em cada hora de um dia útil -- a mesma da Etapa 1
DEMANDA = {0: 40, 1: 30, 2: 25, 3: 25, 4: 30, 5: 60, 6: 180, 7: 1150, 8: 960, 9: 520,
           10: 400, 11: 380, 12: 330, 13: 640, 14: 450, 15: 360, 16: 340, 17: 300,
           18: 260, 19: 200, 20: 150, 21: 110, 22: 80, 23: 55}
CAPACIDADE = 150    # req/min que uma instancia aguenta antes de degradar
ASG = "agenda-web-asg"
PASSO = 15          # segundos reais por passo = 15 minutos simulados

p = argparse.ArgumentParser()
p.add_argument("--inicio", type=int, default=5)
p.add_argument("--fim", type=int, default=19)
p.add_argument("--fator", type=float, default=1.0, help="multiplica a demanda (0.5 em PCs com pouca RAM)")
p.add_argument("--saida", default="resultado.csv")
p.add_argument("--url", default="http://localhost:8080/")
args = p.parse_args()

asg = boto3.client("autoscaling")
cw = boto3.client("cloudwatch")


def capacidade_atual():
    g = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG])["AutoScalingGroups"][0]
    em_servico = sum(1 for i in g["Instances"] if i["LifecycleState"] == "InService")
    return em_servico, g["DesiredCapacity"]


def amostra_http(qtd):
    """Envia algumas requisicoes reais ao ALB e conta quais instancias responderam."""
    quem, erros = collections.Counter(), 0
    for _ in range(qtd):
        try:
            corpo = urllib.request.urlopen(args.url, timeout=1).read().decode()
            quem[corpo.split("Atendido por: ")[-1].split("<")[0]] += 1
        except Exception:
            erros += 1
    return quem, erros


with open(args.saida, "w", newline="") as f:
    out = csv.writer(f)
    out.writerow(["hora", "minuto", "demanda", "em_servico", "desejada",
                  "req_por_instancia", "situacao", "erros_http"])
    for hora in range(args.inicio, args.fim + 1):
        for minuto in (0, 15, 30, 45):
            t0 = time.time()
            with open("relogio.json", "w") as r:          # o controlador le este relogio
                json.dump({"hora": hora + minuto / 60}, r)
            demanda = DEMANDA[hora] * args.fator
            n, desejada = capacidade_atual()
            rpi = demanda / max(n, 1)
            cw.put_metric_data(Namespace="AgendaSaude/Portal", MetricData=[{
                "MetricName": "RequisicoesPorInstancia",
                "Dimensions": [{"Name": "AutoScalingGroupName", "Value": ASG}],
                "Value": rpi, "Unit": "Count"}])
            situacao = "SATURADO" if rpi > CAPACIDADE else "ok"
            quem, erros = amostra_http(max(1, math.ceil(demanda / 100)))
            out.writerow([hora, minuto, round(demanda), n, desejada, round(rpi, 1), situacao, erros])
            f.flush()
            print(f"{hora:02d}:{minuto:02d} demanda={demanda:5.0f} em_servico={n:2d} "
                  f"desejada={desejada:2d} req/inst={rpi:6.1f} {situacao:8s} "
                  f"instancias_respondendo={len(quem)} erros={erros}", flush=True)
            time.sleep(max(0, PASSO - (time.time() - t0)))
