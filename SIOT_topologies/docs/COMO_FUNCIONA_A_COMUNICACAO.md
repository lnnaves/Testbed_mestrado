# Como funciona a comunicação e a medição — por baixo dos panos

> **Escopo deste documento:** explicação detalhada da **lógica de funcionamento**
> do testbed: como a autoridade e os drones se comunicam, como a chave de grupo é
> cifrada/transmitida/decifrada, o que trafega em cada canal, e **o que e como
> exatamente é medido**. É o material de referência para explicar o funcionamento
> interno.
>
> Para a teoria (naïve vs LKH), veja **[`FUNDAMENTACAO_TEORICA.md`](./FUNDAMENTACAO_TEORICA.md)**.
> Para interpretar os números, veja **[`INTERPRETACAO_DOS_RESULTADOS.md`](./INTERPRETACAO_DOS_RESULTADOS.md)**.

---

## 0. A ideia mais importante: existem DOIS canais separados

O erro mais comum ao explicar este testbed é misturar os dois canais. Eles são
**independentes**, usam **protocolos diferentes** e servem a **propósitos diferentes**:

| | **Canal de controle** (protocolo/rekey) | **Canal de dados** (tráfego) |
|---|---|---|
| Protocolo | **TCP** | **UDP** |
| Quem fala | **auth ↔ drone** (estrela) | **drone → drone** (broadcast) |
| Porta | 9000 (auth) e 9100 (cada drone) | 5001 |
| O que transporta | chaves cifradas, ACKs, registro | telemetria simulada (mensagens de exemplo) |
| Programa | `group_auth.py` | `traffic_agent.py` |
| É onde se mede... | **latência de rekey** (`rekey_e2e_ms`) | **perda de pacotes** (Figura 2) |

> **Ponto-chave:** a **chave de grupo NUNCA trafega no canal de dados (UDP)**. Ela é
> distribuída **exclusivamente pelo canal de controle (TCP)**, ponto a ponto entre a
> autoridade e cada drone. O canal de dados só carrega o tráfego "de aplicação"
> (telemetria fictícia) para observar o impacto da revogação na disponibilidade.

---

## 1. Topologia: quem é quem na rede

- **1 autoridade central (`auth1`)** — IP `10.0.0.100`. É um contêiner Docker que
  também é uma estação Wi-Fi. Mantém todo o estado do grupo.
- **N drones (`drone1`, `drone2`, ...)** — cada um é um contêiner + estação Wi-Fi.
- Todos estão na **mesma rede ad hoc (IBSS)**, sem Access Point — comunicação
  direta por rádio emulado (Mininet-WiFi).

A comunicação de **controle** é em **estrela**: cada drone fala com o `auth1`, e o
`auth1` fala com cada drone. **Os drones não trocam chaves entre si** — quem
coordena tudo é a autoridade.

---

## 2. Canal de CONTROLE (TCP) — auth ↔ drones

Este é o canal do protocolo de grupo (`group_auth.py`). Duas "pontas de escuta":

- **A autoridade escuta na porta 9000.** É para lá que os drones mandam
  `register`, `join`, `leave`, `status` e para onde a revogação é disparada.
- **Cada drone escuta na porta 9100** (o "rekey listener"). É para lá que a
  autoridade **empurra (push)** a nova chave cifrada.

Toda mensagem é um **JSON de uma linha** enviado por TCP. Exemplo de um push de rekey:

```json
{"event":"rekey_push","group_id":"mission-alpha","epoch":2,
 "member_id":"drone2","ciphertext_b64":"<chave de grupo cifrada>","timestamp":"..."}
```

E a resposta do drone (o ACK):

```json
{"status":"ack","drone_id":"drone2","epoch":2}
```

---

## 3. As duas chaves e as duas primitivas (o coração criptográfico)

| Chave | Quem tem | Para que serve |
|---|---|---|
| **KEK** (Key Encryption Key) | cada drone tem a **sua**, compartilhada só com o auth | cifrar/decifrar **outras chaves** |
| **Chave de grupo** (group/traffic key) | todos os membros ativos | seria a chave que cifra o tráfego do grupo |

A distribuição segura funciona por **"envelope"**: o auth cifra a **chave de grupo**
sob a **KEK individual** de cada drone. Só aquele drone (dono da KEK) consegue abrir.

A cifra é **AES-GCM real** (não simulada), autenticada (detecta adulteração):

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L92-L106
def _encrypt(key, plaintext):
    nonce = os.urandom(12)                              # nonce aleatório de 96 bits
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ciphertext                           # devolve nonce ‖ ciphertext

def _decrypt(key, nonce_and_ciphertext):
    nonce = nonce_and_ciphertext[:12]                   # extrai o nonce
    ciphertext = nonce_and_ciphertext[12:]
    return AESGCM(key).decrypt(nonce, ciphertext, None) # decifra + verifica a tag GCM
```

- **"Encaps" (encapsulamento):** aqui = `_encrypt(KEK, chave_de_grupo)` → produz o
  envelope. **Não é KEM assimétrico** (não há chave pública/Diffie-Hellman); é
  **cifra simétrica de chave sob chave**.
- **"Decaps":** `_decrypt(KEK, envelope)` → o drone recupera a chave de grupo.
- **Tamanhos:** chave AES-128 = 16 B; tag GCM = 16 B; nonce = 12 B. O envelope cru
  tem ~44 B (depois vira base64 para caber no JSON).

---

## 4. Fase de BOOTSTRAP — os drones entram e recebem sua KEK

Ordem exata quando um drone sobe:

1. O drone **abre seu próprio listener TCP na porta 9100** (para receber pushes
   futuros) — **antes** de falar com o auth.
2. O drone envia `register` para o auth (porta 9000).
3. O auth **cria a KEK individual** daquele drone, guarda o **IP** dele (extraído da
   própria conexão TCP) e **devolve a KEK** na resposta (`kek_b64`).
4. O drone **guarda a KEK** localmente. A partir daí, auth e drone compartilham um
   segredo.

No auth (`register`):

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L490-L499
kek = self.member_kek.setdefault(drone_id, _new_key())
return {
    "status": "accepted", "event": "register", "drone_id": drone_id,
    "group_id": self.group_id, "epoch": self.epoch,
    "members": sorted(self.members),
    "kek_b64": _b64e(kek),          # entrega a KEK individual ao drone
}
```

E o auth descobre o endereço do drone pela conexão:

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L694-L699
if drone_id and event in {"register", "join", "leave", "status"}:
    self.group_state.update_member_endpoint(
        drone_id=drone_id, ip=peer[0], port=member_port   # peer[0] = IP de origem do TCP
    )
```

> **Pergunta: os drones sabem quem são do grupo?**
> **Não diretamente entre si — a autoridade é a fonte da verdade.** O auth mantém a
> lista de membros. Cada drone recebe a lista atual (`members`) nas respostas e a cada
> **heartbeat** (a cada 5 s ele manda `status` e o auth responde com `members`,
> `revoked`, `epoch`). Ou seja, o drone sabe quem está no grupo **porque a autoridade
> informa**, não porque os drones se anunciam mutuamente.

---

## 5. Depois de formado o grupo — os drones "se comunicam"?

**Sim, mas apenas no canal de DADOS (UDP), e não sobre o protocolo.** Depois do
bootstrap, o cenário inicia o tráfego de aplicação simulado:

- Alguns drones viram **receptores** UDP (porta 5001).
- Um drone vira **emissor** e manda mensagens de telemetria fictícia em **broadcast**
  (`10.0.0.255:5001`), ex.: 10 pacotes por segundo.

```python name=common.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/common.py#L500-L509
def start_receiver(drone, port=5001):
    drone.cmd(f"{TRAFFIC_BIN} --role receiver --port {port} ... &")
```

No cenário:

```python name=topology_group_revocation.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/topology_group_revocation.py#L125-L134
for drone in drones:
    start_receiver(drone)                                  # todos escutam UDP:5001
...
start_sender(drone1, dst="10.0.0.255", port=5001, rate=traffic_rate)   # drone1 emite
```

> **⚠️ Ressalva de honestidade (importante para a banca):** esse tráfego de dados
> é **telemetria fictícia** para observar o *impacto* dos eventos na rede — ele **NÃO
> é cifrado com a chave de grupo** no testbed atual. A chave de grupo é real e é
> distribuída de verdade (canal TCP), mas o *payload* UDP em si é texto de exemplo.
> Em outras palavras: medimos o **custo de distribuir a chave** (o foco do trabalho),
> não a cifragem do tráfego de aplicação. O tráfego de dados serve para a **Figura 2**
> (perda de pacotes ao redor da revogação), que é **complementar**.

---

## 6. A REVOGAÇÃO — passo a passo por baixo dos panos

Quando o cenário revoga o `drone3`, ele executa o `group_auth.py` **dentro do
contêiner do auth**, de forma **síncrona** (bloqueia até terminar, para não perder as
métricas):

```python name=common.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/common.py#L475-L490
def revoke_member(auth, target, group_id="mission-alpha"):
    # Intencionalmente sem "&": bloqueia até o revoke terminar para garantir
    # que as métricas de rekey (incluindo ACKs) sejam concluídas antes de seguir.
    auth.cmd(f"{PROTOCOL_BIN} --role auth-server --event revoke "
             f"--target {target} --group-id {group_id} --auth-server 127.0.0.1:9000 ...")
```

### Passo 1 — O auth atualiza o estado e gera a nova chave

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L558-L582
def revoke(self, drone_id):
    self.members.remove(drone_id)          # tira do grupo
    self.member_kek.pop(drone_id, None)    # APAGA a KEK do revogado  ← exclusão efetiva
    self.member_endpoint.pop(drone_id, None)  # esquece o endereço dele
    self.revoked.add(drone_id)             # marca como revogado (não volta)
    self.epoch += 1                        # nova versão da chave
    n_msgs, n_ops, rekey_ms = self._do_rekey_remove(drone_id)  # gera a nova chave (mede CPU)
```

Como a nova chave é gerada difere por esquema:
- **naïve:** gera 1 chave de grupo nova e a cifra **N−1 vezes** (uma por membro
  restante) → **O(n)**.
- **LKH:** re-chaveia só o **caminho da árvore** (folha→raiz) → **~O(log n)**.

### Passo 2 — Preparar os envelopes (encaps por membro)

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L454-L465
for member_id in self.members:
    endpoint = self.member_endpoint.get(member_id)     # onde está o drone (IP:9100)
    kek = self.member_kek.setdefault(member_id, _new_key())
    ciphertext = _encrypt(kek, group_key)              # cifra a chave de grupo sob a KEK do membro
    targets.append({"member_id": member_id, "host": endpoint[0],
                    "port": endpoint[1], "ciphertext_b64": _b64e(ciphertext)})
```

### Passo 3 — Transmitir pela rede e CRONOMETRAR (aqui nasce o `rekey_e2e_ms`)

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L636-L668
t0 = time.perf_counter()                               # ▶️ LIGA O CRONÔMETRO
for target in targets:                                 # um a um (SEQUENCIAL)
    payload = {"event": "rekey_push", "epoch": ...,
               "ciphertext_b64": target["ciphertext_b64"], ...}
    ok, ack_response, sent_bytes, err = cls._send_push_and_wait_ack(
        target["host"], target["port"], payload)       # envia via TCP e ESPERA o ACK
    total_bytes += sent_bytes                           # soma bytes transmitidos
    if ok: acked.append(target["member_id"])
    else:  failed.append(...)
rekey_e2e_ms = (time.perf_counter() - t0) * 1000.0      # ⏹️ PARA no último ACK
response["acks_received"] = len(acked)
response["acks_expected"] = len(targets)
```

### Passo 4 — O drone recebe, decifra (decaps), instala e confirma (ACK)

```python name=group_auth.py url=https://github.com/lnnaves/Testbed_mestrado/blob/main/SIOT_topologies/scripts/group_auth.py#L846-L860
ciphertext = _b64d(ciphertext_b64)                     # desfaz base64
member_kek = self.member_ctx.get("member_kek")         # a KEK recebida no bootstrap
group_key = _decrypt(member_kek, ciphertext)           # DECAPS: decifra a chave de grupo
self.member_ctx["group_key"] = group_key               # INSTALA a nova chave
self.member_ctx["epoch"] = epoch
response = {"status": "ack", "drone_id": ..., "epoch": epoch}   # ✅ confirma
```

> **Por que o `drone3` fica de fora:** no Passo 1 o auth **apagou a KEK e o endereço**
> dele. Logo, ele **não recebe** o push e **não tem** como decifrar a nova chave de
> grupo. Mesmo continuando fisicamente no alcance, ele foi **excluído
> criptograficamente** (forward secrecy). É exatamente o que o cenário quer testar:
> **exclusão lógica, não desconexão física.**

---

## 7. O que é medido, onde e como (exato)

### 7.1 As métricas de rekey (canal de CONTROLE / TCP)

Todas medidas **dentro da autoridade**, gravadas na linha `revoke` do
`protocol_latency.csv`:

| Métrica | O que é | Onde/como é medido |
|---|---|---|
| **`rekey_e2e_ms`** ⭐ | latência **end-to-end** do rekey | cronômetro do **1º envio** até o **último ACK** (Passo 3) |
| `rekey_ms` | tempo de **CPU** (gerar+cifrar) | cronômetro só em volta da geração da chave (Passo 1) |
| `rekey_msgs` | nº de mensagens de rekey | contador incrementado a cada envio/cifragem |
| `crypto_ops` | nº de cifragens AES-GCM | contador a cada `_encrypt` |
| `rekey_bytes_total` | bytes transmitidos na rede | soma do tamanho de cada mensagem TCP enviada |
| `acks_received` / `acks_expected` | quantos confirmaram vs esperados | contagem de ACKs no laço (Passo 3) |

> **`rekey_bytes_total` mede exatamente o quê?** O número de bytes do **JSON de push
> enviado** pela autoridade a cada membro (a linha TCP, em bytes). É a **carga de
> controle** injetada na rede pelo rekey — **não** inclui o tráfego de dados UDP.

### 7.2 As métricas de RTT e perda (canal de DADOS / UDP e pings)

- **RTT (ping):** o cenário mede latência de ida-e-volta entre nós em várias fases
  (antes/depois da revogação) com `ping`. Vai para o CSV de métricas exploratórias.
- **Perda de pacotes (Figura 2):** o receptor UDP conta, por janela de tempo, quantos
  pacotes esperava vs recebeu (a partir dos números de sequência) → `traffic_loss.csv`.
  Serve para ver o impacto da revogação na **disponibilidade** do tráfego legítimo.

---

## 8. Linha do tempo de um experimento (o cenário completo)

Ordem real de eventos (do `topology_group_revocation.py`):

```
1. scenario_start        → cria auth1 + N drones na rede ad hoc
2. auth_server_start     → sobe o auth (porta 9000) com o esquema de rekey escolhido
3. member_auth (×N)      → cada drone sobe listener (9100), registra e recebe sua KEK
4. RTT pré-revogação     → mede latência de rede (baseline)
5. traffic_start         → drones viram receptores UDP; drone1 emite telemetria (broadcast)
6. malicious_traffic     → drone3 passa a agir de forma maliciosa (usa chave antiga)
7. revocation_requested  → AUTH REVOGA drone3:
                             • remove drone3, apaga KEK+IP dele, epoch++
                             • gera nova chave (naïve N−1 / LKH ~log N)  → rekey_ms
                             • ▶️ push TCP para cada membro → decaps → ACK
                             • ⏹️ rekey_e2e_ms = 1º envio → último ACK
                             • grava a linha no protocol_latency.csv
8. RTT pós-revogação     → mede latência depois do rekey
9. tráfego continua      → drone2 emite; verifica que os legítimos seguem se comunicando
10. collect CSVs         → copia protocol_latency.csv e traffic_loss.csv p/ o host
11. scenario_end         → encerra a rede
```

---

## 9. Perguntas frequentes (respostas diretas)

**A chave de grupo trafega no tráfego (UDP)?**
Não. A chave só trafega no **canal de controle (TCP)**, cifrada, ponto a ponto entre
o auth e cada drone. O UDP carrega apenas telemetria de exemplo.

**Os drones se comunicam entre si?**
No **canal de dados (UDP)**, sim (telemetria em broadcast). No **protocolo/rekey**,
não — cada drone só fala com a autoridade (topologia em estrela).

**Os drones sabem quem é do grupo?**
Sabem pela **autoridade**, não por descoberta mútua: recebem a lista de membros nas
respostas e nos heartbeats periódicos. A autoridade é a fonte da verdade.

**A comunicação da chave é medida no tráfego TCP?**
Sim. A distribuição da chave é feita por **TCP real** na rede ad hoc emulada, e é
essa troca (envio → ACK) que é cronometrada (`rekey_e2e_ms`) e contada em bytes
(`rekey_bytes_total`).

**É KEM (encapsulamento assimétrico, tipo Kyber)?**
Não. É **cifra simétrica AES-GCM** de chave-sob-chave (a KEK é pré-compartilhada no
bootstrap). "Encaps/decaps" aqui significa cifrar/decifrar a chave de grupo sob a KEK.

**Como o revogado fica de fora?**
A autoridade **apaga a KEK e o endereço** dele na revogação. Sem KEK, ele não decifra
a nova chave; sem endereço, ele não recebe o push. Continua no alcance físico, mas
está **fora criptograficamente**.

**Por que o envio é sequencial e não broadcast?**
É uma escolha de modelagem: enviar um a um e esperar cada ACK modela um **pior caso
realista** e torna visível a diferença naïve (N−1 envios) vs LKH (~log N envios).

---

## 10. Resumo em um parágrafo

O testbed tem **dois canais**: um de **controle (TCP)**, em estrela entre a autoridade
e cada drone, por onde as **chaves cifradas** e os **ACKs** trafegam; e um de **dados
(UDP)**, em broadcast entre drones, com telemetria de exemplo para observar
disponibilidade. No bootstrap, cada drone recebe da autoridade sua **KEK individual**.
Na revogação, a autoridade gera uma **nova chave de grupo**, cifra-a sob a KEK de cada
membro restante (**encaps**), **transmite por TCP**, e cada drone **decifra (decaps)**
e **confirma (ACK)**. A métrica principal, **`rekey_e2e_ms`**, é o tempo do primeiro
envio até o último ACK — a **latência real de re-securização da rede**. O drone
revogado, sem KEK, fica **criptograficamente excluído**.
