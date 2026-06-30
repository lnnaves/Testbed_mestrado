# Fundamentação Teórica — Autenticação de Grupo e Rekeying em Redes de Drones

> **Escopo deste documento:** material teórico que fundamenta o testbed. Explica
> os conceitos de autenticação de grupo, gerenciamento de chaves, os esquemas
> naïve e LKH, e o conceito de testbed emulado.
>
> Para **como rodar** o testbed, veja **[`../README.md`](../README.md)**.
> Para a **descrição técnica do código**, veja **[`../RELATORIO_TESTBED.md`](../RELATORIO_TESTBED.md)**.

---

## 1. O problema: comunicação segura em grupo

Em uma missão com múltiplos drones (um *swarm*), os nós precisam trocar mensagens entre si — telemetria, comandos e coordenação de voo. Essa comunicação costuma ser **em grupo** (um-para-muitos ou muitos-para-muitos).

Para proteger a comunicação (confidencialidade e integridade), o grupo compartilha uma **chave de grupo** (*group key*, TEK). Quem tem a chave lê; quem não tem, não lê.

Isso impõe três requisitos centrais:

1. **Autenticação de grupo** — só membros legítimos devem entrar no grupo.
2. **Forward secrecy** — membro removido não deve ler tráfego futuro.
3. **Backward secrecy** — membro novo não deve ler tráfego passado.

Os dois últimos requisitos são o núcleo do problema de **rekeying**.

---

## 2. Por que a chave de grupo precisa mudar: o problema do rekeying

Se um drone comprometido conhece a chave atual `K_grupo` e é apenas “removido da lista”, ele ainda consegue decifrar o tráfego futuro. Portanto, a revogação só é efetiva se houver **nova chave de grupo** `K_grupo'` distribuída apenas aos membros válidos.

No design atual do testbed, esse processo é medido como **evento de rede completo**, não apenas como custo local:

1. A autoridade gera/recalcula o material de rekey.
2. A autoridade faz **push TCP** da nova chave cifrada para cada membro restante.
3. Cada membro **decifra com sua KEK individual** e responde **ACK**.
4. O sistema mede o tempo total até o último ACK (**`rekey_e2e_ms`**).

Assim, além de custo de mensagens/cripto, a pergunta central passa a incluir a **latência real de propagação do rekey na rede ad hoc**.

---

## 3. Conceitos criptográficos de base

### 3.1 KEK (*Key Encryption Key*)

Chave usada para cifrar outras chaves. Cada membro mantém uma **KEK individual**, compartilhada com a autoridade.

### 3.2 TEK (*Traffic Encryption Key*)

Chave de tráfego do grupo; é a chave usada para cifrar dados entre drones.

### 3.3 AES-GCM

As operações de cifragem do testbed usam AES-GCM real. O testbed não “simula” criptografia: ele executa operações reais de cifra/decifra.

---

## 4. Modelo de autenticação de grupo do testbed

O modelo é **centralizado** na autoridade lógica (`auth1`), que mantém estado de membros, revogados, epoch e material criptográfico.

Eventos de ciclo de vida:

| Evento | O que acontece | Dispara rekey? |
|---|---|---|
| **register** | Registro inicial no grupo | Não |
| **join** | Entrada de novo membro | Sim |
| **leave** | Saída voluntária | Sim |
| **revoke** | Expulsão de membro comprometido | **Sim** (evento central) |

No fluxo atual, `register`/`join` também entregam `kek_b64` ao membro, permitindo decifrar pushes futuros de rekey.

---

## 5. Os dois esquemas de rekeying

### 5.1 Naïve — O(n)

A autoridade cifra material de rekey para cada membro remanescente. O número de transmissões cresce linearmente com N.

### 5.2 LKH — O(log n)

A autoridade usa uma árvore de chaves e atualiza apenas o caminho afetado. O número de operações/transmissões cresce aproximadamente com `log2(N)`.

### 5.3 O que é comparado na prática

| Aspecto | Naïve | LKH |
|---|---|---|
| Mensagens de rekey | `N-1` (O(n)) | `~log2(N)` (O(log n)) |
| Operações cripto | `N-1` | `~log2(N)` |
| Latência E2E de propagação (`rekey_e2e_ms`) | tende a subir com N | tende a subir mais lentamente |
| Escalabilidade | limitada | melhor |

---

## 6. O conceito teórico do testbed (emulação)

### 6.1 Por que emulação

A emulação (Containernet + Mininet-WiFi) usa processos reais e stack de rede real, com reprodutibilidade melhor que hardware físico e maior realismo que simulação pura.

### 6.2 Blocos do testbed

- **Containernet:** nós como contêineres Docker.
- **Mininet-WiFi:** rede sem fio ad hoc emulada.
- **IBSS/ad hoc:** comunicação sem AP central.

### 6.3 Cenário experimental de revogação

1. Forma-se o grupo.
2. Tráfego legítimo começa.
3. Um drone comprometido é revogado.
4. O auth executa rekey e distribui material cifrado por push.
5. Membros decifram e respondem ACK.
6. Mede-se custo de rekey (Figura 1) e perda de pacotes (Figura 2).

### 6.4 Metodologia de medição

- **Repetições (runs):** média e desvio padrão.
- **Varredura de N:** observa escalabilidade (naïve vs LKH).
- **Medição instrumentada:** custo lógico (`rekey_msgs`, `crypto_ops`) + tempo local (`rekey_ms`) + custo de rede (`rekey_e2e_ms`, `rekey_bytes_total`, ACKs).

### 6.5 Medição da latência end-to-end do rekey

A latência **`rekey_e2e_ms`** mede o tempo do começo da distribuição até o último ACK recebido. Essa métrica representa o tempo real para a rede voltar a um estado seguro após a revogação.

Além dela, o testbed mede:

- **`rekey_bytes_total`**: bytes totais transmitidos no rekey;
- **`acks_received` / `acks_expected`**: completude da rodada de distribuição.

Quanto à Figura 2 (perda de pacotes), ela é mantida como evidência **complementar**: a revogação é lógica (o revogado pode continuar no alcance físico) e, com tráfego leve (10 pps), a perda tende a ficar baixa ou dominada por ruído da emulação.

### 6.6 Por que latência end-to-end é a métrica principal

1. **`rekey_ms` mede CPU do host, não de drone real.** Todos os contêineres compartilham a CPU do host; logo, esse tempo não generaliza para hardware embarcado restrito.
2. **Sem medir rede, Mininet-WiFi perde o sentido metodológico.** Se a avaliação fosse só CPU/contadores, Docker puro bastaria. O valor do testbed está na emulação da rede ad hoc.
3. **Throughput não é o ponto aqui; latência é.** O payload do material principal de rekey é minúsculo (≈32 bytes: 16 da chave AES-128 + 16 da tag GCM). Mesmo no pior caso naïve com N=32, o volume total fica na ordem de ~1 KB. O canal não satura por capacidade; o que importa é quão rápido a nova chave chega aos membros válidos.

---

## 7. Conceitos de segurança avaliados, em resumo

| Conceito | Definição | Como o testbed se relaciona |
|---|---|---|
| **Autenticação de grupo** | Só membros legítimos obtêm chave de grupo | Autoridade valida register/join |
| **Forward secrecy** | Ex-membro não decifra tráfego futuro | Rekey em leave/revoke |
| **Backward secrecy** | Novo membro não decifra tráfego passado | Rekey em join |
| **Revogação** | Exclusão criptográfica de membro comprometido | Evento central da campanha |
| **Escalabilidade de rekeying** | Como custo cresce com N | Naïve O(n) vs LKH O(log n) |
| **Latência de re-chaveamento** | Tempo para o grupo inteiro receber a nova chave | `rekey_e2e_ms` (métrica principal) |

---

## 8. Posicionamento na literatura

- Group key management com forward/backward secrecy é tema clássico.
- LKH reduz custo de O(n) para O(log n) via hierarquia de chaves.
- Em redes de drones, custo de rekey afeta disponibilidade e tempo de reação do sistema.
- Este testbed conecta teoria de complexidade com medição prática em rede ad hoc emulada.

---

## 9. Glossário rápido

| Termo | Significado |
|---|---|
| **TEK** | Chave de tráfego do grupo |
| **KEK** | Chave para cifrar material de chave |
| **Rekeying** | Geração e redistribuição de nova chave de grupo |
| **Push** | Entrega ativa do auth para o membro via TCP |
| **ACK** | Confirmação de recebimento da nova chave pelo membro |
| **`rekey_e2e_ms`** | Latência end-to-end do rekey (até o último ACK) |
| **`rekey_bytes_total`** | Total de bytes transmitidos no rekey |
| **Epoch** | Versão da chave de grupo |
| **LKH** | Rekey em árvore com custo O(log n) |
| **Ad hoc / IBSS** | Rede sem fio sem Access Point |

---

## 10. Resumo em um parágrafo

Este testbed compara naïve e LKH no rekeying de grupo em rede ad hoc de drones, mantendo criptografia real e medição reproduzível. No design atual, a nova chave é realmente distribuída na rede (push TCP), os membros decifram com KEK individual e confirmam por ACK. Por isso, a métrica central de desempenho é a **latência end-to-end de propagação** (`rekey_e2e_ms`), complementada por `rekey_bytes_total` e contadores de ACK; `rekey_ms` (tempo de CPU do auth no host) permanece como referência secundária. A Figura 2 (perda de pacotes) continua útil como evidência complementar de disponibilidade, mas não substitui a latência E2E como métrica principal do rekey.
