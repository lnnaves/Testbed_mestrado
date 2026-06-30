# Fundamentação Teórica — Autenticação de Grupo e Rekeying em Redes de Drones

> **Escopo deste documento:** material teórico que fundamenta o testbed. Explica
> os conceitos de autenticação de grupo, gerenciamento de chaves, os esquemas
> naïve e LKH, e o conceito de testbed emulado.
>
> Para **como rodar** o testbed, veja **[`../README.md`](../README.md)**.
> Para a **descrição técnica do código**, veja **[`../RELATORIO_TESTBED.md`](../RELATORIO_TESTBED.md)**.

---

## 1. O problema: comunicação segura em grupo

Em uma missão com múltiplos drones (um *swarm*), os nós precisam trocar mensagens entre si — telemetria, comandos, coordenação de voo. Frequentemente essa comunicação é **em grupo** (um-para-muitos ou muitos-para-muitos): um drone líder envia uma ordem que **todos** devem receber, ou sensores transmitem dados para o grupo inteiro.

Para proteger essa comunicação (confidencialidade e integridade), o grupo compartilha uma **chave de grupo** (*group key*, ou *Traffic Encryption Key* — TEK). Toda mensagem do grupo é cifrada com essa chave. Quem tem a chave lê; quem não tem, não lê.

Isso cria três requisitos de segurança centrais:

1. **Autenticação de grupo** — garantir que só drones **legítimos e autorizados** entrem no grupo e obtenham a chave.
2. **Forward secrecy (sigilo futuro)** — quando um membro **sai ou é expulso**, ele **não** deve conseguir decifrar as comunicações **futuras** do grupo.
3. **Backward secrecy (sigilo retroativo)** — quando um membro **entra**, ele **não** deve conseguir decifrar as comunicações **passadas** do grupo.

Os dois últimos requisitos são o coração do problema de **gerenciamento de chaves de grupo** (*group key management*).

---

## 2. Por que a chave de grupo precisa mudar: o problema do rekeying

Imagine um grupo de 4 drones compartilhando a chave `K_grupo`. Tudo funciona até que um drone seja **comprometido** (capturado, invadido, ou detectado agindo de forma maliciosa). Esse drone **conhece `K_grupo`**.

Se você simplesmente expulsar o drone da lista de membros mas **mantiver a mesma chave**, não adianta nada: ele ainda tem `K_grupo` e continua decifrando tudo que o grupo transmite. A revogação seria apenas "lógica", sem efeito criptográfico real.

A solução é o **rekeying** (re-chaveamento): ao expulsar um membro, gera-se uma **nova** chave de grupo `K_grupo'` e a distribui **somente aos membros restantes**, de forma que o membro expulso **não** a receba. A partir daí, o grupo cifra com `K_grupo'`, e o ex-membro fica de fora.

O mesmo raciocínio vale para **entrada** de membros (para garantir backward secrecy) e **saída voluntária**.

**A pergunta central de pesquisa do testbed é:** *qual é o custo desse rekeying, e como ele escala com o tamanho do grupo?*

Esse custo importa muito em drones porque eles têm **recursos limitados**: bateria, CPU, e principalmente **largura de banda do rádio**. Um esquema de rekeying que envia muitas mensagens ou faz muitas operações criptográficas drena bateria e congestiona o canal — exatamente o que não se pode ter em uma missão crítica.

---

## 3. Conceitos criptográficos de base

Antes dos esquemas, três conceitos fundamentais:

### 3.1 Chave de Cifração de Chave (KEK — *Key Encryption Key*)

É uma chave usada **não para cifrar dados**, mas para **cifrar outras chaves**. Cada membro do grupo possui uma **KEK individual**, conhecida apenas por ele e pela autoridade. Para entregar a nova chave de grupo a um membro de forma segura, a autoridade **cifra** `K_grupo'` com a KEK daquele membro. Só ele consegue decifrar e obter a nova chave.

### 3.2 Chave de Tráfego (TEK / *group key*)

É a chave que realmente cifra os **dados** trocados no grupo. É ela que muda a cada evento de rekeying.

### 3.3 Cifra simétrica autenticada (AES-GCM)

No testbed, as operações de cifragem usam **AES-GCM** (Galois/Counter Mode), uma cifra simétrica que fornece **confidencialidade + integridade/autenticidade** ao mesmo tempo. Cada operação de "cifrar uma chave sob uma KEK" é, na prática, **uma operação AES-GCM real** — e é isso que o testbed **conta e cronometra** para medir custo de forma honesta.

> **Nota de honestidade científica:** o protocolo do testbed é um **esquema de referência** para *medir* o custo de rekeying, não uma nova proposta padronizada. A criptografia, porém, é **real** — não é simulada. Isso dá validade às medições de tempo e de número de operações.

---

## 4. Modelo de autenticação de grupo do testbed

O testbed adota um modelo **centralizado** de autoridade:

- Existe uma **Autoridade Central** (chamada `auth` / `auth1` no código), que é uma entidade **lógica** — ela coordena o grupo, mas **não** é infraestrutura de rede (não é um Access Point). Participa da rede ad hoc como qualquer outro nó.
- A autoridade mantém o **estado do grupo**: quem são os membros, quem foi revogado, qual a **época** (epoch) atual, e o material criptográfico (KEKs individuais e a chave de grupo).
- Os **drones** se autenticam junto à autoridade e recebem dela a chave de grupo.

**Eventos do ciclo de vida do grupo:**

| Evento | O que acontece | Dispara rekey? |
|---|---|---|
| **register** | Drone se registra inicialmente no grupo | Não (só entra na lista) |
| **join** | Novo membro entra no grupo | Sim (backward secrecy) |
| **leave** | Membro sai voluntariamente | Sim (forward secrecy) |
| **revoke** | Autoridade **expulsa** um membro comprometido | **Sim** (forward secrecy) — evento central da campanha |

O conceito de **época (epoch)** é importante: cada rekeying incrementa o epoch, funcionando como um "número de versão" da chave de grupo. Membros sabem em qual época estão, e mensagens podem ser associadas a uma época — o que ajuda a detectar quem está usando chave antiga (por exemplo, o drone revogado tentando continuar transmitindo).

---

## 5. Os dois esquemas de rekeying

Esta é a comparação central do trabalho. Ambos resolvem o **mesmo problema** (distribuir uma nova chave de grupo aos membros válidos), mas com **custos de escalabilidade radicalmente diferentes**.

### 5.1 Esquema Naïve (ingênuo) — O(n)

A abordagem mais direta possível:

1. A autoridade gera uma nova chave de grupo `K_grupo'`.
2. Para **cada** membro restante, ela cifra `K_grupo'` com a **KEK individual** daquele membro.
3. Envia cada cópia cifrada ao respectivo membro.

```
Grupo com N membros, 1 e' revogado -> restam N-1 membros.

K_grupo' cifrada para membro 1   (1 mensagem, 1 operacao cripto)
K_grupo' cifrada para membro 2   (1 mensagem, 1 operacao cripto)
K_grupo' cifrada para membro 3   (1 mensagem, 1 operacao cripto)
...
K_grupo' cifrada para membro N-1 (1 mensagem, 1 operacao cripto)
```

**Custo:** `N - 1` mensagens e `N - 1` operações criptográficas por revogação. Em notação assintótica: **O(n)**.

**Problema:** o custo cresce **linearmente** com o tamanho do grupo. Para 4 drones, são 3 mensagens — trivial. Mas para 1000 drones, são 999 mensagens **a cada** evento de associação. Em um swarm grande com membros entrando/saindo frequentemente, isso satura o canal de rádio e drena bateria.

### 5.2 Esquema LKH (Logical Key Hierarchy) — O(log n)

O **LKH** é a solução clássica da literatura para esse problema de escalabilidade. A ideia central: em vez de tratar cada membro isoladamente, organize as chaves em uma **árvore binária**.

**Estrutura da árvore:**

```
                    [ K_raiz ]              <- chave de grupo derivada daqui
                   /          \
            [ K_no_A ]      [ K_no_B ]      <- KEKs intermediarias
             /     \          /     \
          [d1]    [d2]     [d3]    [d4]     <- folhas = KEK individual de cada drone
```

- Cada **folha** corresponde a um drone e contém a **KEK individual** dele (que só ele e a autoridade conhecem).
- Cada **nó interno** contém uma **KEK intermediária**, conhecida por **todos os drones daquela subárvore**.
- A **raiz** dá origem à **chave de grupo**, conhecida por todos.

**Princípio-chave:** cada drone conhece **todas as chaves no caminho da sua folha até a raiz** (e nenhuma outra). No exemplo, `d1` conhece: sua própria KEK, `K_no_A` e `K_raiz`. Ele **não** conhece `K_no_B` nem a KEK de `d2`.

**O que acontece numa revogação (ex.: revogar `d3`):**

Quando `d3` é expulso, **todas as chaves que ele conhecia** ficam comprometidas e precisam ser trocadas — ou seja, as chaves no **caminho de `d3` até a raiz**: `K_no_B` e `K_raiz`. As outras (a subárvore de `d1`/`d2`) **não** precisam mudar, porque `d3` nunca as conheceu.

Para cada chave nova nesse caminho, a autoridade a cifra para as **subárvores filhas** que devem recebê-la:

```
Revogar d3:
1. Nova K_no_B' -> cifrar para d4 (d3 sai, sobra d4 na subarvore B)   [1 msg]
2. Nova K_raiz' -> cifrar para subarvore A (com K_no_A)               [1 msg]
                -> cifrar para subarvore B (com K_no_B')              [1 msg]
```

**Custo:** proporcional à **altura da árvore**, que é `log2(N)`. Em notação assintótica: **O(log n)**.

**Por que isso é tão melhor:** o número de chaves que precisam ser trocadas é o comprimento de **um caminho** na árvore, não o número total de membros. A árvore "agrupa" os membros, permitindo re-chavear blocos inteiros com uma só mensagem (cifrando para uma KEK intermediária que vários membros compartilham).

### 5.3 A comparação que o testbed mede

| Aspecto | Naïve | LKH |
|---|---|---|
| Mensagens por revogação | `N - 1` -> **O(n)** | `~log2(N)` -> **O(log n)** |
| Operações cripto | `N - 1` | `~log2(N)` |
| Estado mantido | 1 KEK por membro | árvore de chaves (folhas + nós internos) |
| Complexidade de implementação | baixa | moderada (gerencia a árvore) |
| Escalabilidade | ruim em grupos grandes | excelente |

**Exemplo numérico (mensagens por revogação):**

| N (tamanho do grupo) | Naïve (N-1) | LKH (~log2 N) |
|---|---|---|
| 4 | 3 | ~2-3 |
| 8 | 7 | ~3-4 |
| 16 | 15 | ~4-5 |
| 32 | 31 | ~5-6 |
| 1000 | 999 | ~10 |

A diferença é modesta para grupos pequenos, mas torna-se **dramática** conforme o grupo cresce. É exatamente essa curva — naïve subindo linearmente, LKH quase plana — que a **Figura 1** do testbed evidencia (especialmente com eixo Y logarítmico).

---

## 6. O conceito teórico do testbed (emulação)

### 6.1 Por que um testbed emulado, e não simulação pura ou hardware real

Há três formas de avaliar um protocolo de rede:

| Abordagem | Realismo | Custo / esforço | Reprodutibilidade |
|---|---|---|---|
| **Simulação** (ex.: ns-3) | modela comportamento, abstrai o SO/stack real | baixo | alta |
| **Emulação** (Containernet/Mininet) | usa **stack de rede real** do Linux + processos reais | médio | alta |
| **Testbed físico** (drones reais) | realismo máximo | altíssimo, difícil repetir | baixa |

O testbed escolhe a **emulação**, que é um **meio-termo** poderoso: roda **código real** (a criptografia AES-GCM acontece de verdade, os processos trocam mensagens TCP reais) sobre uma **stack de rede Linux real**, mas tudo em uma única máquina, de forma **reproduzível** e sem o custo/risco de drones físicos.

### 6.2 Os blocos do testbed

**Containernet** — extensão do Mininet que permite usar **contêineres Docker** como nós da rede. Cada drone e a autoridade são, simultaneamente:

- um **contêiner Docker** (com seu próprio sistema de arquivos, processos e o agente de protocolo rodando dentro);
- um **nó de rede** na topologia emulada.

**Mininet-WiFi** — extensão do Mininet que adiciona **redes sem fio** emuladas: estações Wi-Fi, modelos de propagação de rádio, posições espaciais e alcance. É o que permite modelar drones como **estações Wi-Fi móveis** em uma **rede ad hoc**.

**Rede ad hoc (IBSS)** — diferentemente de uma rede Wi-Fi tradicional (com Access Point central), uma rede **ad hoc** é descentralizada: os nós se comunicam diretamente entre si, sem infraestrutura. Isso modela bem um swarm de drones em campo, onde não há roteador no céu. No testbed, **todos os nós** (drones + autoridade) entram no mesmo SSID ad hoc.

**Modelo de propagação (logDistance)** — o Mininet-WiFi calcula a conectividade entre nós com base em **posição** e **alcance de rádio**, usando um modelo de perda de sinal por distância. Isso permite cenários onde um drone está "fora de alcance" e precisa se aproximar — relevante para os cenários de join/leave.

### 6.3 O cenário experimental (revogação)

O cenário central que a campanha executa modela uma **situação de segurança realista**:

```
1. Forma-se o grupo: autoridade + N drones, todos autenticados.
2. Trafego legitimo flui entre os drones (cifrado com a chave de grupo).
3. Um drone (drone3) e' COMPROMETIDO -> passa a emitir trafego malicioso,
   tentando usar a chave antiga.
4. A autoridade DETECTA e REVOGA o drone3 -> dispara o rekeying.
5. Mede-se:
   - o CUSTO do rekey (mensagens, operacoes cripto, tempo)  -> Figura 1
   - a PERDA de pacotes legitimos em torno da revogacao      -> Figura 2
```

Este desenho permite avaliar **duas dimensões**:

- **Eficiência do rekeying** (Figura 1): quanto custa expulsar um membro, em função de N e do esquema.
- **Impacto na disponibilidade** (Figura 2): quanto o tráfego legítimo é perturbado durante a transição de chave.

### 6.4 Metodologia de medição

- **Repetições (runs):** cada configuração (esquema × N) é executada **R vezes** (ex.: 10) para obter **média e desvio padrão**, dando significância estatística às curvas. Isso é essencial porque emulação tem variabilidade (escalonamento de CPU, jitter da stack de rede).
- **Varredura de N:** testar N em {4, 8, 16, 32} permite **observar a curva de escalabilidade** — é a varredura que revela O(n) vs O(log n) na prática.
- **Métricas honestas:** o custo é medido **dentro** do agente que executa o rekeying (contando operações AES-GCM reais e cronometrando o tempo de re-chaveamento), não estimado por fórmula. As mensagens são contadas pela convenção: *número de mensagens de rekey emitidas pela autoridade*.

---

## 7. Conceitos de segurança avaliados, em resumo

| Conceito | Definição | Como o testbed se relaciona |
|---|---|---|
| **Autenticação de grupo** | Garantir que só membros legítimos obtenham a chave de grupo | Autoridade central valida register/join |
| **Forward secrecy** | Ex-membro não decifra tráfego futuro | Rekeying na saída/revogação |
| **Backward secrecy** | Novo membro não decifra tráfego passado | Rekeying na entrada (join) |
| **Revogação** | Expulsar criptograficamente um membro comprometido | Evento central da campanha |
| **Escalabilidade de rekeying** | Como o custo cresce com N | Comparação naïve O(n) vs LKH O(log n) |

---

## 8. Posicionamento na literatura

- O problema de **group key management** com forward/backward secrecy é clássico em **multicast seguro** e **comunicação em grupo**.
- O **LKH** foi proposto no contexto de multicast seguro escalável (trabalhos seminais de **Wong, Gouda & Lam** e **Wallner, Harder & Agee**, fim dos anos 1990), justamente para reduzir o custo de rekeying de O(n) para O(log n) usando uma hierarquia de chaves em árvore.
- A aplicação a **redes de drones / UAV swarms** é motivada pelas **restrições de recursos** (energia, banda) desses dispositivos, onde o custo de rekeying tem impacto direto na viabilidade da missão.
- O testbed se posiciona como uma **avaliação empírica** desse custo em ambiente **emulado realista** (rede ad hoc Wi-Fi + criptografia real), preenchendo a lacuna entre a análise teórica de complexidade (O(n) vs O(log n)) e a medição prática sob uma stack de rede real.

> **Recomendação:** confirme as citações exatas (Wong et al., 1998/2000; Wallner et al., RFC 2627) nas fontes originais antes de incluir na bibliografia do mestrado, para garantir formatação e datas corretas.

---

## 9. Glossário rápido

| Termo | Significado |
|---|---|
| **TEK** (*Traffic Encryption Key*) | Chave que cifra os dados do grupo (= chave de grupo) |
| **KEK** (*Key Encryption Key*) | Chave usada para cifrar outras chaves |
| **Rekeying** | Processo de gerar e redistribuir uma nova chave de grupo |
| **Forward secrecy** | Ex-membro não decifra tráfego futuro |
| **Backward secrecy** | Novo membro não decifra tráfego passado |
| **LKH** (*Logical Key Hierarchy*) | Esquema de rekeying em árvore, custo O(log n) |
| **Epoch** | "Versão" da chave de grupo; incrementa a cada rekeying |
| **Ad hoc / IBSS** | Rede sem fio descentralizada, sem Access Point |
| **AES-GCM** | Cifra simétrica autenticada usada nas operações |
| **Emulação** | Execução de código/stack reais em ambiente controlado |

---

## 10. Resumo em um parágrafo

Este testbed avalia, de forma empírica e reprodutível, o **custo de re-chaveamento de chaves de grupo** ao revogar um drone comprometido em uma rede ad hoc de UAVs. Ele compara o esquema **naïve** (que re-cifra a nova chave individualmente para cada membro, custo **O(n)**) com o **LKH** (que organiza as chaves em árvore binária e re-chaveia apenas o caminho da folha à raiz, custo **O(log n)**). Usando **emulação** (Containernet + Mininet-WiFi) com ****
