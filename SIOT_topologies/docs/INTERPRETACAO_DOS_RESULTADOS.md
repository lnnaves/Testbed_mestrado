# Como ler e interpretar os resultados do testbed

> **Escopo deste documento:** guia prático para **ler, validar e interpretar** os
> dados produzidos pela campanha (`figure1_rekey_cost.csv` e as figuras), com
> exemplos numéricos reais. Foca em *o que cada número significa* e *como contar
> a história* na dissertação.
>
> Para **como rodar**, veja **[`../README.md`](../README.md)**.
> Para a **teoria**, veja **[`FUNDAMENTACAO_TEORICA.md`](./FUNDAMENTACAO_TEORICA.md)**.
> Para as **métricas em si**, veja **[`METRICAS_DO_TESTBED.md`](./METRICAS_DO_TESTBED.md)**.

---

## 1. Onde estão os resultados

Depois de uma campanha (`run_campaign.py --results-dir ./campaign-results`):

| Arquivo | O que é |
|---|---|
| `figure1_rekey_cost.csv` | **Uma linha por evento de revoke por run.** É a fonte de tudo. |
| `figure2_packet_loss.csv` | Perda de pacotes ao longo do tempo (métrica complementar). |
| `figure1_rekey_cost.(png\|pdf)` | Gráfico do custo vs N. |
| `figure2_packet_loss.(png\|pdf)` | Gráfico de perda vs tempo. |
| `raw/<esquema>-N<tamanho>/run-<id>/` | CSVs brutos coletados dos contêineres. |

O arquivo central é o **`figure1_rekey_cost.csv`**. Tudo neste guia gira em torno dele.

---

## 2. Anatomia de uma linha (com exemplo real)

Cabeçalho e uma linha real medida:

```csv
rekey_scheme,group_size,run_id,rekey_msgs,crypto_ops,rekey_ms,rekey_e2e_ms,rekey_bytes_total,acks_received,acks_expected
naive,3,0,3,3,0.693,5.529,807,3,3
```

O que cada coluna significa:

| Coluna | Valor no exemplo | Significado |
|---|---|---|
| `rekey_scheme` | `naive` | Esquema de rekey usado (`naive` ou `lkh`). |
| `group_size` | `3` | **Membros que receberam a nova chave** (= N − 1 após o revoke). Veja §6. |
| `run_id` | `0` | Número da repetição. |
| `rekey_msgs` | `3` | Mensagens de rekey emitidas pela autoridade. |
| `crypto_ops` | `3` | Operações AES-GCM reais executadas. |
| `rekey_ms` | `0.693` | **Tempo de CPU** (gerar + cifrar) no host. *Métrica secundária.* |
| `rekey_e2e_ms` | `5.529` | **Latência end-to-end:** do início do rekey até o último ACK. ⭐ *Métrica principal.* |
| `rekey_bytes_total` | `807` | Bytes efetivamente transmitidos na rede no rekey. |
| `acks_received` | `3` | Quantos membros confirmaram o recebimento. |
| `acks_expected` | `3` | Quantos deveriam confirmar. |

---

## 3. A PRIMEIRA coisa a checar: o run é válido?

Antes de interpretar qualquer custo, valide a integridade do run:

> **Regra de ouro:** o run só é confiável se **`acks_received == acks_expected`.**

No exemplo: `3 == 3` ✅ → **todos os membros receberam, decifraram e confirmaram a nova chave.** Run válido.

Se `acks_received < acks_expected`, alguns ACKs não chegaram a tempo (estouraram o
timeout do push). Esse run está **incompleto** e o `rekey_e2e_ms` dele é
**subestimado** (mediu só até os que responderam). Filtre ou investigue esses runs.

**Comando para encontrar runs incompletos:**

```bash
awk -F, 'NR>1 && $9!=$10 {print "INCOMPLETO:", $0}' ./campaign-results/figure1_rekey_cost.csv
# nenhuma saída = todos os runs completos
```

> ⚠️ Runs incompletos tendem a aparecer em **N grande** (ex.: N=32 → 31 pushes
> sequenciais), quando a máquina host fica saturada com muitos contêineres. Se
> acontecer, considere aumentar o timeout de ACK ou rodar N=32 separadamente.

---

## 4. A métrica PRINCIPAL: `rekey_e2e_ms` (latência end-to-end)

Esta é a métrica central do trabalho. Ela mede o **tempo real para a rede de
drones voltar a um estado seguro** após a revogação: do instante em que a
autoridade começa a distribuir a nova chave até o **último membro confirmar**
o recebimento (ACK).

**Por que ela é a principal (e não o `rekey_ms`):**

1. **`rekey_ms` é tempo de CPU do *host*, não de um drone.** Todos os contêineres
   compartilham a CPU potente da sua máquina; esse número **não generaliza** para
   o hardware fraco de um drone real. Um drone levaria muito mais tempo para cifrar.
2. **O valor do Mininet-WiFi está em medir a *rede*.** Se só medíssemos CPU,
   bastaria Docker puro. A latência E2E captura a propagação pela **rede ad hoc
   emulada** — que é o que realmente importa em um swarm.
3. **A latência E2E escala com o esquema:** naïve faz N−1 transmissões sequenciais
   (cresce com N); LKH faz ~log(N) (quase plano). É exatamente o que a figura mostra.

### Exemplo numérico (a comparação que valida a tese)

Da linha real:

```
rekey_ms     = 0.693 ms   (só CPU: gerar + cifrar)
rekey_e2e_ms = 5.529 ms   (CPU + transmitir + decifrar + confirmar)
```

- A **latência de rede é ~8× o tempo de CPU.**
- O **custo de rede puro** ≈ `5.529 − 0.693 = 4.836 ms` (a parcela de transmissão/ACK).
- **Conclusão:** medir só `rekey_ms` ignoraria ~87% do custo real do rekey.

> Esta é a evidência empírica de que **o custo do rekeying está na rede, não na CPU** —
> e por isso a latência E2E é a métrica certa para uma rede de drones.

---

## 5. As métricas de apoio

### 5.1 `rekey_msgs` e `crypto_ops` — a complexidade (O(n) vs O(log n))

Confirmam a teoria de escalabilidade, **agora validados por transmissão real**:

- **naïve:** `rekey_msgs = N − 1` (uma mensagem por membro restante) → **O(n)**.
- **lkh:** `rekey_msgs ≈ log2(N)` (só o caminho da árvore) → **O(log n)**.

No exemplo (naïve, 3 membros): `rekey_msgs = 3 = N−1` ✅ e `crypto_ops = 3` (uma
cifragem AES-GCM por mensagem). Consistente.

### 5.2 `rekey_bytes_total` — carga no canal

Total de bytes transmitidos na rede durante o rekey. **Não é throughput** (vazão);
é o **volume total** injetado no canal sem fio.

No exemplo: `807 bytes` para 3 mensagens → **~269 bytes/mensagem**. Coerente: cada
push é um JSON contendo o ciphertext (~32 bytes da chave + tag, em base64) mais os
campos de envelope (`event`, `group_id`, `epoch`, `member_id`, `timestamp`).

**Interpretação:** o naïve injeta `~269 × (N−1)` bytes por revogação → cresce
**linearmente**. O LKH injeta `~269 × O(log N)` → muito menos. É o argumento de
**eficiência de uso do canal** (o naïve "polui" mais a rede).

### 5.3 `rekey_ms` — tempo de CPU (secundário)

Tempo local do auth para gerar a nova chave e cifrá-la para cada membro. **Métrica
secundária**, mantida como referência e contraste didático com a latência E2E.
**Sempre acompanhe-a da ressalva** de que é medida no host, não em hardware de drone.

---

## 6. ⚠️ Ponto crítico: `group_size` é N − 1 (membros que receberam)

**Atenção a isto ao ler as figuras.** A coluna `group_size` registra os membros
que **receberam** a nova chave — ou seja, **N − 1** (o grupo original menos o
drone revogado).

| `--num-drones` (N original) | drone revogado | `group_size` no CSV |
|---|---|---|
| 4 | drone3 | **3** |
| 8 | drone3 | **7** |
| 16 | drone3 | **15** |
| 32 | drone3 | **31** |

Por isso, no exemplo, `group_size = 3` mesmo tendo rodado com `--num-drones 4`.

**Consequência prática:** o eixo X da Figura 1 vai mostrar **3, 7, 15, 31**, não
4, 8, 16, 32. Isso **não é um erro** — é até mais correto, pois o custo é
proporcional aos membros que *recebem* o rekey. Mas **declare isso na dissertação**:
*"o eixo N representa os membros que receberam a nova chave (N − 1 após a revogação)."*

---

## 7. Como gerar e ler as figuras

```bash
# devolve a posse dos arquivos (campanha roda com sudo)
sudo chown -R "$USER:$USER" ./campaign-results

# FIGURA PRINCIPAL: latência end-to-end vs N (naïve vs LKH)
python3 plot_figures.py --results-dir ./campaign-results --metric rekey_e2e_ms

# figuras de apoio
python3 plot_figures.py --results-dir ./campaign-results --metric rekey_bytes_total
python3 plot_figures.py --results-dir ./campaign-results --metric rekey_msgs --fig1-logy
python3 plot_figures.py --results-dir ./campaign-results --metric rekey_ms      # CPU (secundária)
```

### O que esperar ver (a hipótese)

Na Figura 1 com `--metric rekey_e2e_ms`, comparando as duas curvas:

| N (membros) | naïve (O(n)) | LKH (O(log n)) |
|---|---|---|
| 3 | baseline (~5–6 ms) | similar (grupo pequeno) |
| 7 | ~2× o baseline | quase igual |
| 15 | sobe forte | sobe pouco |
| 31 | **muito alto** | **ainda baixo** |

- **naïve subindo** (mais membros → mais pushes sequenciais → mais latência).
- **LKH quase plano** (poucas mensagens, independente de N).
- As **barras de erro** são o desvio padrão sobre os runs (por isso `--runs 10`).

> Essa separação visual — naïve crescente vs LKH plano, **em latência real de rede** —
> é o **resultado central** da dissertação.

---

## 8. Como agregar os runs (média ± desvio)

O `plot_figures.py` já agrega automaticamente: para cada `(esquema, N)`, calcula
**média** e **desvio padrão** sobre os `run_id`. Por isso roda-se com `--runs 10`
(mais runs = barras de erro mais confiáveis).

Se quiser inspecionar manualmente (ex.: a média do `rekey_e2e_ms` por célula):

```bash
# media de rekey_e2e_ms por (esquema, group_size)
awk -F, 'NR>1 {sum[$1","$2]+=$7; n[$1","$2]++}
         END {for (k in sum) printf "%s  media_e2e_ms=%.3f  (n=%d)\n", k, sum[k]/n[k], n[k]}' \
    ./campaign-results/figure1_rekey_cost.csv | sort
```

---

## 9. Checklist de validação dos resultados

Antes de usar os números na dissertação, confirme:

- [ ] **Todos os runs completos:** `acks_received == acks_expected` em todas as linhas (§3).
- [ ] **Contagem de mensagens coerente:** naïve com `rekey_msgs == group_size`; LKH com `rekey_msgs ≈ log2(group_size+1)`.
- [ ] **`rekey_e2e_ms > rekey_ms`** em todas as linhas (a rede sempre custa mais que a CPU).
- [ ] **Número de linhas esperado:** `nº de esquemas × nº de N × nº de runs`. Ex.: 2 × 4 × 10 = **80 linhas** de dados.
- [ ] **`rekey_bytes_total` cresce com N no naïve** e cresce devagar no LKH.
- [ ] **Sem outliers absurdos:** um `rekey_e2e_ms` 100× maior que os vizinhos pode ser jitter de CPU do host — investigue ou trate como outlier.

---

## 10. Como redigir (modelo de parágrafo para a dissertação)

> *"A Figura X apresenta a latência end-to-end de re-chaveamento (`rekey_e2e_ms`)
> em função do número de membros que recebem a nova chave após a revogação, para
> os esquemas naïve e LKH, em uma rede ad hoc emulada (Containernet + Mininet-WiFi).
> Cada ponto é a média de 10 repetições, com barras de erro indicando o desvio
> padrão. Diferentemente do tempo de processamento criptográfico local
> (`rekey_ms`), medido no host e portanto não representativo do hardware embarcado
> de um drone, a latência end-to-end captura o custo real de propagação da nova
> chave pela rede sem fio, incluindo transmissão, decifragem e confirmação (ACK)
> por cada membro. Observa-se que o esquema naïve cresce linearmente com o número
> de membros (O(n)), pois a autoridade transmite a nova chave individualmente a
> cada um, enquanto o LKH permanece aproximadamente constante (O(log n)), por
> re-chavear apenas o caminho afetado da árvore. A título de exemplo, em uma
> revogação com 3 membros remanescentes, mediu-se `rekey_e2e_ms = 5,5 ms` contra
> `rekey_ms = 0,7 ms`, evidenciando que cerca de 87 % do custo do rekeying decorre
> da rede, e não do processamento criptográfico."*

---

## 11. Resumo em uma frase

A métrica que importa é a **latência end-to-end (`rekey_e2e_ms`)** — o tempo real
para a rede de drones se re-securizar após a revogação; valide sempre que
**`acks_received == acks_expected`**, lembre que **`group_size` é N − 1**, e use o
**naïve crescente vs LKH plano** como o resultado central.
