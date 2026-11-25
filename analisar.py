"""Compara os cenarios A e B da Etapa 5 com uma frota fixa dimensionada para o pico."""
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FROTA_FIXA = 11      # instancias da frota fixa (sua resposta da Etapa 1)
PASSO_H = 0.25       # cada linha do CSV vale 15 minutos


def ler(nome):
    with open(nome) as f:
        return list(csv.DictReader(f))


cenarios = {"A (so dinamica)": ler("cenario-A.csv"), "B (agendada + dinamica)": ler("cenario-B.csv")}
print(f"{'cenario':26s} {'inst-hora':>10s} {'passos saturados':>17s} {'economia vs fixa':>17s}")
for nome, linhas in cenarios.items():
    inst_hora = sum(int(l["em_servico"]) for l in linhas) * PASSO_H
    fixa = FROTA_FIXA * len(linhas) * PASSO_H
    saturados = sum(1 for l in linhas if l["situacao"] == "SATURADO")
    print(f"{nome:26s} {inst_hora:10.1f} {saturados:17d} {1 - inst_hora / fixa:16.0%}")

fig, ax = plt.subplots(figsize=(10, 4.5))
for nome, linhas in cenarios.items():
    x = [int(l["hora"]) + int(l["minuto"]) / 60 for l in linhas]
    ax.step(x, [int(l["em_servico"]) for l in linhas], where="post", label=f"Cenario {nome}")
linhas = next(iter(cenarios.values()))
x = [int(l["hora"]) + int(l["minuto"]) / 60 for l in linhas]
ax.step(x, [int(l["demanda"]) / 105 for l in linhas], where="post", linestyle="--", color="gray",
        label="Necessario (demanda / 105)")
ax.axhline(FROTA_FIXA, color="black", linewidth=0.8, label=f"Frota fixa ({FROTA_FIXA})")
ax.set_xlabel("hora simulada"); ax.set_ylabel("instancias em servico")
ax.set_title("Instancias em servico ao longo do dia simulado"); ax.legend(); fig.tight_layout()
fig.savefig("comparativo.png", dpi=150)
print("grafico salvo em comparativo.png")
