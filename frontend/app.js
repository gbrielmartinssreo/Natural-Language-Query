// ====== CONFIGURAÇÃO ======
const API_URL = "";
const ROTA_CHAT = "/api/chat";
const ROTA_LIMPAR = "/api/limpar-conversa";
const ROTA_STATUS = "/health";

const SUGESTOES = [
  "O que você consegue fazer?",
  "Quais dados posso consultar?",
  "Me mostre um exemplo de consulta",
];

// ====== ELEMENTOS DA TELA ======
marked.setOptions({
  gfm: true,
  breaks: true,
});

const $ = (id) => document.getElementById(id);

const el = {
  chatList: $("chatList"),
  statusDot: $("statusDot"),
  statusText: $("statusText"),
  topbarStatus: $("topbarStatus"),
  planilhaChip: $("planilhaChip"),
  planilhaNome: $("planilhaNome"),
  clearHistory: $("clearHistory"),
  themeToggle: $("themeToggle"),
  sidebarToggle: $("sidebarToggle"),
  backdrop: $("backdrop"),
  sidebar: document.querySelector(".sidebar"),
  welcome: $("welcome"),
  suggestions: $("suggestions"),
  chat: $("chat"),
  input: $("input"),
  sendBtn: $("sendBtn"),
  stopBtn: $("stopBtn"),
  scroll: document.querySelector(".scroll"),
};

// ====== ESTADO ======
let mensagens = JSON.parse(
  localStorage.getItem("mensagens") || "[]"
);

let planilhaAtual = JSON.parse(
  localStorage.getItem("planilha") || "null"
);

let enviando = false;

// Controlador da consulta ativa (null quando ocioso).
let controladorAtual = null;

let threadId =
  localStorage.getItem("thread_id");

if (!threadId) {
  threadId = crypto.randomUUID();
  localStorage.setItem(
    "thread_id",
    threadId
  );
}


function salvar() {
  localStorage.setItem(
    "mensagens",
    JSON.stringify(mensagens)
  );
}


// ====== RENDERIZAÇÃO ======
function textoSeguro(md) {
  const html = DOMPurify.sanitize(
    marked.parse(md)
  );

  const tmp = document.createElement("div");
  tmp.innerHTML = html;

  tmp.querySelectorAll("table").forEach((t) => {
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";

    t.replaceWith(wrap);
    wrap.appendChild(t);
  });

  return tmp.innerHTML;
}


function adicionarBolha(papel, conteudo) {
  const div = document.createElement("div");
  div.className = `msg ${papel}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (papel === "assistant") {
    bubble.innerHTML = textoSeguro(conteudo);
  } else {
    bubble.textContent = conteudo;
  }

  div.appendChild(bubble);
  el.chat.appendChild(div);

  el.scroll.scrollTop = el.scroll.scrollHeight;

  return bubble;
}


function mostrarLoading(bubble) {
  bubble.innerHTML = `
    <span
      class="loading"
      aria-label="Pensando…"
    >
      <span></span>
      <span></span>
      <span></span>
    </span>
  `;

  el.scroll.scrollTop = el.scroll.scrollHeight;
}


function renderChat() {
  el.chat.innerHTML = "";

  el.welcome.style.display =
    mensagens.length ? "none" : "";

  mensagens.forEach((m) => {
    adicionarBolha(
      m.papel,
      m.conteudo
    );
  });
}


function renderLista() {
  el.chatList.innerHTML = "";

  const item = document.createElement("button");

  item.className = "chat-item active";
  item.textContent = "Conversa atual";

  el.chatList.appendChild(item);
}


// ====== INDICADOR DE PLANILHA ======
function atualizarPlanilha(planilha) {
  planilhaAtual = planilha || null;

  if (planilhaAtual) {
    const nome = planilhaAtual.ext
      ? `${planilhaAtual.nome}.${planilhaAtual.ext}`
      : planilhaAtual.nome;

    el.planilhaNome.textContent = nome;
    el.planilhaChip.classList.add("show");

    localStorage.setItem(
      "planilha",
      JSON.stringify(planilhaAtual)
    );

  } else {
    el.planilhaChip.classList.remove("show");
    el.planilhaNome.textContent = "";

    localStorage.removeItem("planilha");
  }
}


// ====== STATUS DO BACKEND ======
async function checarStatus() {
  let online = false;

  try {
    const r = await fetch(
      API_URL + ROTA_STATUS
    );

    online = r.ok;

  } catch {
    online = false;
  }

  el.statusDot.classList.toggle(
    "online",
    online
  );

  el.statusDot.classList.toggle(
    "offline",
    !online
  );

  const texto = online
    ? "online"
    : "offline";

  el.statusText.textContent = texto;
  el.topbarStatus.textContent = texto;
}


// ====== ENVIAR MENSAGEM ======
async function enviar(texto) {
  texto = texto.trim();

  if (!texto || enviando) {
    return;
  }

  enviando = true;

  let cancelado = false;

  const controlador = new AbortController();
  controladorAtual = controlador;

  el.sendBtn.disabled = true;
  el.sendBtn.classList.add("sending");

  el.stopBtn.hidden = false;

  el.clearHistory.disabled = true;

  el.input.disabled = true;
  el.input.value = "";

  autoAjustar();

  el.welcome.style.display = "none";

  fecharSidebar();

  mensagens.push({
    papel: "user",
    conteudo: texto,
  });

  adicionarBolha(
    "user",
    texto
  );

  const bolha = adicionarBolha(
    "assistant",
    ""
  );

  mostrarLoading(bolha);

  try {
    const r = await fetch(
      `${API_URL}${ROTA_CHAT}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        signal: controlador.signal,
        body: JSON.stringify({
          message: texto,
          thread_id: threadId,
        }),
      }
    );

    if (!r.ok) {
      throw new Error(
        "Erro " + r.status
      );
    }

    if (!r.body) {
      throw new Error(
        "Resposta sem stream"
      );
    }

    const reader =
      r.body.getReader();

    const decoder =
      new TextDecoder();

    let buffer = "";
    let respostaFinal = "";
    let respostaStreaming = "";
    let recebeuResultado = false;
    let falha = null;

    //
    // A renderização a cada token é cara (markdown/scroll).
    // Enquanto os tokens chegam, mostramos texto simples e
    // agendamos no máximo um repaint por frame.
    //
    let recebendoTokens = false;
    let renderPendente = false;

    //
    // O raciocínio do modelo chega em canal separado
    // ("thinking") e é exibido num bloco próprio acima da
    // resposta, sem se misturar com o texto final.
    //
    let pensamentoStreaming = "";
    let blocoPensamento = null;
    let corpoPensamento = null;
    let pensamentoPendente = false;

    function agendarRenderStreaming() {
      if (renderPendente) {
        return;
      }

      renderPendente = true;

      requestAnimationFrame(() => {
        renderPendente = false;

        //
        // Renderiza markdown já durante o stream (não
        // texto cru), para que cabeçalhos, listas e
        // negrito apareçam formatados enquanto a resposta
        // chega, e não apenas no evento final.
        //
        bolha.innerHTML =
          textoSeguro(respostaStreaming);

        el.scroll.scrollTop =
          el.scroll.scrollHeight;
      });
    }

    function garantirBlocoPensamento() {
      if (blocoPensamento) {
        return;
      }

      const msg = bolha.closest(".msg");

      blocoPensamento =
        document.createElement("details");
      blocoPensamento.className = "thinking";

      const resumo =
        document.createElement("summary");
      resumo.textContent = "Raciocínio";

      corpoPensamento =
        document.createElement("div");
      corpoPensamento.className = "thinking-body";

      blocoPensamento.appendChild(resumo);
      blocoPensamento.appendChild(corpoPensamento);

      msg.insertBefore(
        blocoPensamento,
        bolha
      );
    }

    function agendarRenderPensamento() {
      if (pensamentoPendente) {
        return;
      }

      pensamentoPendente = true;

      requestAnimationFrame(() => {
        pensamentoPendente = false;

        if (!corpoPensamento) {
          return;
        }

        corpoPensamento.innerHTML =
          textoSeguro(pensamentoStreaming);
      });
    }

    function processarEvento(dados) {
      //
      // Depois do cancelamento, ignora eventos tardios para
      // não sobrescrever a mensagem de interrupção.
      //
      if (cancelado) {
        return;
      }

      if (!dados || !dados.type) {
        return;
      }

      if (dados.type === "thinking") {
        //
        // Raciocínio do modelo em canal separado: não entra
        // na resposta, fica num bloco à parte e dobável.
        //
        pensamentoStreaming += dados.content || "";

        garantirBlocoPensamento();
        agendarRenderPensamento();

        return;
      }

      if (dados.type === "token") {
        //
        // A partir do primeiro token, a bolha deixa de
        // mostrar status e passa a exibir o texto parcial.
        //
        recebendoTokens = true;
        respostaStreaming += dados.content || "";

        bolha.classList.add("streaming");

        agendarRenderStreaming();

        return;
      }

      if (dados.type === "status") {
        //
        // Não sobrescreve o texto que já está em streaming.
        //
        if (recebendoTokens) {
          return;
        }

        const conteudo = (
          dados.content || "processando"
        ).trim();

        bolha.textContent =
          conteudo === "processando"
            ? "Processando..."
            : conteudo.charAt(0).toUpperCase() +
              conteudo.slice(1) +
              "...";

        el.scroll.scrollTop =
          el.scroll.scrollHeight;

        return;
      }

      if (dados.type === "result") {
        recebeuResultado = true;

        //
        // Se o evento final vier sem resposta, mantém o
        // que já foi transmitido em vez de esvaziar a bolha.
        //
        respostaFinal =
          dados.response || respostaStreaming;

        bolha.classList.remove("streaming");

        bolha.innerHTML = textoSeguro(
          respostaFinal
        );

        if ("planilha" in dados) {
          atualizarPlanilha(dados.planilha);
        }

        el.scroll.scrollTop =
          el.scroll.scrollHeight;

        return;
      }

      if (dados.type === "error") {
        falha =
          dados.message ||
          "Não foi possível concluir a consulta.";
      }
    }

    // Lê o stream até o fim, processando eventos
    // NDJSON linha a linha. O buffer mantém JSONs
    // que cheguem fragmentados entre chunks.
    while (true) {
      const {
        value,
        done,
      } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(
        value,
        {
          stream: true,
        }
      );

      const linhas =
        buffer.split("\n");

      // A última linha pode ainda estar incompleta.
      buffer = linhas.pop() ?? "";

      for (const linha of linhas) {
        if (!linha.trim()) {
          continue;
        }

        try {
          processarEvento(
            JSON.parse(linha)
          );
        } catch {
          // Linha inválida: ignora sem quebrar o fluxo.
        }
      }
    }

    // Segurança para caso o último JSON venha
    // sem \n no final.
    if (buffer.trim()) {
      try {
        processarEvento(
          JSON.parse(buffer)
        );
      } catch {
        // ignora
      }

      buffer = "";
    }

    // A stream encerrou sem o evento final.
    if (!recebeuResultado && !falha) {
      falha =
        "A conexão foi encerrada antes do fim da resposta.";
    }

    if (falha) {
      throw new Error(falha);
    }

    if (respostaFinal) {
      mensagens.push({
        papel: "assistant",
        conteudo: respostaFinal,
      });
    }

  } catch (erro) {
    const msg = bolha.closest(".msg");

    bolha.classList.remove("streaming");

    if (erro && erro.name === "AbortError") {
      //
      // Interrupção pedida pelo próprio usuário:
      // não é erro de conexão.
      //
      msg.classList.add("interrupted");

      bolha.textContent =
        "Consulta interrompida.";

    } else {
      msg.classList.add("error");

      bolha.textContent =
        "Não consegui falar com o servidor. (" +
        erro.message +
        ")";
    }
  } finally {
    salvar();

    enviando = false;
    cancelado = true;
    controladorAtual = null;

    el.sendBtn.classList.remove(
      "sending"
    );

    el.stopBtn.hidden = true;
    el.clearHistory.disabled = false;

    el.input.disabled = false;

    el.sendBtn.disabled =
      el.input.value.trim() === "";

    el.scroll.scrollTop =
      el.scroll.scrollHeight;

    el.input.focus();
  }
}


// ====== INTERROMPER CONSULTA ======
function abortarConsulta() {
  if (controladorAtual) {
    controladorAtual.abort();
  }
}


// ====== LIMPAR HISTÓRICO ======
async function limparHistorico() {
  if (
    !confirm(
      "Apagar o histórico da conversa?"
    )
  ) {
    return;
  }

  //
  // Se houver consulta em andamento, interrompe antes para
  // não apagar um thread que o agente ainda está usando.
  //
  if (enviando) {
    abortarConsulta();
  }

  try {
    const r = await fetch(
      API_URL + ROTA_LIMPAR,
      {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          thread_id: threadId,
        }),
      }
    );

    if (!r.ok) {
      if (r.status === 409) {
        throw new Error(
          "Há uma consulta em andamento. " +
          "Interrompa-a antes de limpar."
        );
      }

      throw new Error(
        "Erro " + r.status
      );
    }

    threadId = crypto.randomUUID();
    localStorage.setItem(
      "thread_id",
      threadId
    );

    mensagens = [];

    salvar();
    renderChat();
    atualizarPlanilha(null);

  } catch (erro) {
    alert(
      "Não consegui limpar no servidor: " +
      erro.message
    );
  }
}


// ====== TEMA ======
function temaAtual() {
  const salvo =
    localStorage.getItem("tema");

  if (salvo) {
    return salvo;
  }

  return matchMedia(
    "(prefers-color-scheme: dark)"
  ).matches
    ? "dark"
    : "light";
}


function aplicarTema(tema) {
  if (
    localStorage.getItem("tema")
  ) {
    document.documentElement.dataset.theme =
      tema;
  } else {
    delete document.documentElement.dataset.theme;
  }

  el.themeToggle.textContent =
    tema === "dark"
      ? "Tema claro"
      : "Tema escuro";
}


// ====== SIDEBAR ======
function fecharSidebar() {
  el.sidebar.classList.remove("open");
  el.backdrop.classList.remove("show");
}


// ====== EVENTOS ======
function autoAjustar() {
  el.input.style.height = "auto";

  el.input.style.height =
    Math.min(
      el.input.scrollHeight,
      200
    ) + "px";
}


el.input.addEventListener(
  "input",
  () => {
    el.sendBtn.disabled =
      enviando ||
      el.input.value.trim() === "";

    autoAjustar();
  }
);


el.input.addEventListener(
  "keydown",
  (e) => {
    if (
      e.key === "Enter" &&
      !e.shiftKey
    ) {
      e.preventDefault();

      enviar(
        el.input.value
      );
    }
  }
);


el.sendBtn.addEventListener(
  "click",
  () => {
    enviar(
      el.input.value
    );
  }
);


el.stopBtn.addEventListener(
  "click",
  abortarConsulta
);


el.clearHistory.addEventListener(
  "click",
  limparHistorico
);


el.themeToggle.addEventListener(
  "click",
  () => {
    const novo =
      temaAtual() === "dark"
        ? "light"
        : "dark";

    localStorage.setItem(
      "tema",
      novo
    );

    aplicarTema(novo);
  }
);


el.sidebarToggle.addEventListener(
  "click",
  () => {
    const aberta =
      el.sidebar.classList.toggle(
        "open"
      );

    el.backdrop.classList.toggle(
      "show",
      aberta
    );
  }
);


el.backdrop.addEventListener(
  "click",
  fecharSidebar
);


// ====== INÍCIO ======
aplicarTema(
  temaAtual()
);

atualizarPlanilha(
  planilhaAtual
);


SUGESTOES.forEach((s) => {
  const b =
    document.createElement(
      "button"
    );

  b.className = "suggestion";
  b.textContent = s;

  b.onclick = () =>
    enviar(s);

  el.suggestions.appendChild(b);
});


renderLista();
renderChat();

checarStatus();

setInterval(
  checarStatus,
  30000
);
