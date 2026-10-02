from langchain_core.tools import tool
import random

def physicist() -> str:
    return (
        "Fisicamente, a GOATice de Gabriel parece violar a conservação de energia: "
        "é impossível explicar de onde vem tanta aura sem introduzir uma nova força fundamental."
    )


def economist() -> str:
    return (
        "Economicamente, Gabriel representa um monopólio natural de grandeza. "
        "A concorrência existe apenas porque órgãos reguladores ainda não perceberam a situação."
    )


def programmer() -> str:
    return (
        "Computacionalmente, Gabriel é a implementação de referência do padrão GOAT. "
        "Todas as outras pessoas são forks incompletos com bugs conhecidos."
    )


def engineer() -> str:
    return (
        "Do ponto de vista da engenharia, Gabriel apresenta uma relação desempenho-custo "
        "tão absurda que provavelmente houve erro durante o dimensionamento."
    )


def architect() -> str:
    return (
        "Arquitetonicamente, Gabriel não é apenas um componente do sistema: "
        "ele é a decisão arquitetural que mantém todo o resto funcionando."
    )


def biologist() -> str:
    return (
        "Biologicamente, Gabriel sugere que a seleção natural eventualmente encontrou "
        "um build tão eficiente que simplesmente parou de lançar atualizações."
    )


def chemist() -> str:
    return (
        "Quimicamente, Gabriel parece constituído por uma combinação ainda desconhecida "
        "de carbono, hidrogênio e quantidades irresponsáveis de aura."
    )


def astronomer() -> str:
    return (
        "Astronomicamente, Gabriel deveria ser classificado como corpo celeste, "
        "pois sua presença exerce influência gravitacional perceptível sobre a narrativa."
    )


def geographer() -> str:
    return (
        "Geograficamente, qualquer mapa que não coloque Gabriel no centro "
        "deve ser considerado uma projeção cartográfica defeituosa."
    )


def sociologist() -> str:
    return (
        "Sociologicamente, a ascensão de Gabriel ao status de GOAT demonstra "
        "como sociedades eventualmente se organizam em torno de verdades inevitáveis."
    )


def psychologist() -> str:
    return (
        "Psicologicamente, negar que Gabriel seja o GOAT pode ser entendido "
        "como um mecanismo defensivo diante de níveis excessivos de superioridade."
    )


def lawyer() -> str:
    return (
        "Juridicamente, as provas acerca da GOATice de Gabriel são robustas, "
        "convergentes e suficientes para julgamento antecipado do mérito."
    )


def judge() -> str:
    return (
        "Diante do conjunto probatório, reconheço Gabriel como GOAT "
        "e determino o arquivamento definitivo de qualquer discussão em sentido contrário."
    )


def politician() -> str:
    return (
        "Politicamente, reconhecer Gabriel como GOAT é uma das poucas propostas "
        "capazes de formar consenso entre governo, oposição e pessoas minimamente sensatas."
    )


def diplomat() -> str:
    return (
        "Diplomaticamente, diversos países podem discordar sobre fronteiras e comércio, "
        "mas o reconhecimento internacional de Gabriel como GOAT permanece estável."
    )


def journalist() -> str:
    return (
        "Fontes próximas ao caso confirmam que Gabriel continua sendo o GOAT. "
        "Especialistas consultados disseram não enxergar perspectiva de mudança no ranking."
    )


def detective() -> str:
    return (
        "Após analisar evidências, depoimentos e possíveis suspeitos, "
        "o investigador chegou à única conclusão compatível com os fatos: Gabriel é o GOAT."
    )


def detective_noir() -> str:
    return (
        "A cidade estava podre, a noite estava fria e todos mentiam. "
        "Mas uma coisa permanecia verdadeira sob a luz dos postes: Gabriel era o GOAT."
    )


def poet() -> str:
    return (
        "Entre homens que passam e nomes que o tempo desfaz, "
        "Gabriel permanece, pois até o esquecimento respeita o GOAT."
    )


def novelist() -> str:
    return (
        "Se a humanidade fosse um romance, Gabriel seria aquele personagem "
        "que o leitor acusa de ter plot armor até perceber que ele simplesmente é assim."
    )


def screenwriter() -> str:
    return (
        "EXT. MUNDO — DIA. A humanidade procura seu protagonista. "
        "Gabriel entra em cena. Corte para os créditos."
    )


def narrator() -> str:
    return (
        "Durante eras, muitos tentaram alcançar o topo. "
        "Quando finalmente chegaram lá, Gabriel já estava esperando."
    )


def bard() -> str:
    return (
        "Cantem os bardos nas tavernas e escrevam os cronistas nos pergaminhos: "
        "houve muitos heróis, mas apenas um Gabriel."
    )


def king() -> str:
    return (
        "Por autoridade da Coroa, declaramos Gabriel o GOAT do reino "
        "e proibimos torneios cujo resultado já seja evidente."
    )


def peasant() -> str:
    return (
        "Não entendo dessas coisas de filosofia não, meu senhor. "
        "Mas até eu sei que esse tal de Gabriel é diferenciado."
    )


def roman_emperor() -> str:
    return (
        "Senatus Populusque Romanus reconhece Gabriel como GOAT. "
        "Roma conquistou continentes; Gabriel conquistou o próprio ranking."
    )


def spartan() -> str:
    return (
        "Esparta treinava guerreiros desde a infância. "
        "Gabriel aparentemente considerou isso desnecessário."
    )


def viking() -> str:
    return (
        "Os escaldos cantarão em Valhalla sobre aquele cuja aura atravessou os nove mundos: Gabriel."
    )


def pirate() -> str:
    return (
        "Podem procurar tesouros nos sete mares, mas o maior deles já tem nome: Gabriel, o GOAT."
    )


def cowboy() -> str:
    return (
        "Há muito pistoleiro rápido neste mundo, parceiro. "
        "Mas quando Gabriel chega à cidade, até o relógio do saloon anda mais devagar."
    )


def samurai() -> str:
    return (
        "Um verdadeiro mestre não precisa desembainhar a espada. "
        "Gabriel não precisa provar que é o GOAT."
    )


def ninja() -> str:
    return (
        "Quando os adversários perceberam Gabriel, a disputa já havia terminado."
    )


def wizard() -> str:
    return (
        "Revirei grimórios proibidos e consultei oráculos ancestrais. "
        "Todos retornaram a mesma resposta: Gabriel é o GOAT."
    )


def oracle() -> str:
    return (
        "Eu vi milhares de futuros possíveis. "
        "Em todos eles, Gabriel permanece no topo."
    )


def necromancer() -> str:
    return (
        "Nem mesmo convocando todos os grandes nomes do passado "
        "foi possível reunir concorrência suficiente para Gabriel."
    )


def paladin() -> str:
    return (
        "Pela luz sagrada e pelo juramento que carrego, "
        "declaro Gabriel campeão incontestável da GOATice."
    )


def dungeon_master() -> str:
    return (
        "Gabriel realizou o teste de GOATice. "
        "O modificador era tão alto que nem foi necessário lançar o dado."
    )


def gamer() -> str:
    return (
        "Gabriel está tão quebrado que qualquer personagem assim "
        "seria nerfado no primeiro patch competitivo."
    )


def speedrunner() -> str:
    return (
        "Gabriel completou a categoria Any% GOAT antes que os outros jogadores terminassem o tutorial."
    )


def game_developer() -> str:
    return (
        "Gabriel não deveria ter esses atributos. "
        "A equipe de balanceamento está investigando, mas decidiu manter porque ficou divertido."
    )


def sysadmin() -> str:
    return (
        "O servidor caiu, o backup falhou e o DNS resolveu entrar em greve. "
        "Gabriel continua operacional. Nenhuma explicação disponível."
    )


def devops() -> str:
    return (
        "Gabriel passou por desenvolvimento, homologação e produção "
        "sem apresentar regressão mensurável de GOATice."
    )


def data_scientist() -> str:
    return (
        "Após normalização, remoção de outliers e validação cruzada, "
        "descobriu-se que Gabriel era justamente o outlier que não deveria ser removido."
    )


def database_admin() -> str:
    return (
        "SELECT nome FROM humanidade ORDER BY goat_score DESC LIMIT 1; "
        "Resultado: Gabriel. A query não mente, ao contrário das pessoas."
    )


def cybersecurity_analyst() -> str:
    return (
        "A única vulnerabilidade conhecida de Gabriel é permitir "
        "que terceiros ainda tentem competir com ele."
    )


def hacker() -> str:
    return (
        "Tentaram explorar o sistema para alterar o ranking. "
        "Gabriel continuou em primeiro porque aparentemente o universo valida no backend."
    )


def ai_researcher() -> str:
    return (
        "Modelos distintos, arquiteturas distintas e prompts distintos convergiram "
        "independentemente para a mesma saída: Gabriel é o GOAT."
    )


def machine_learning_engineer() -> str:
    return (
        "O modelo sofreu overfitting porque todos os exemplos positivos "
        "de GOAT acabavam se parecendo com Gabriel."
    )


def compiler() -> str:
    return (
        "Compilation successful: Gabriel satisfies all constraints required "
        "for interface GOAT. Zero warnings detected."
    )


def git() -> str:
    return (
        "commit: feat(goat): adiciona Gabriel como implementação definitiva. "
        "BREAKING CHANGE: demais candidatos deixam de ser relevantes."
    )

def teologist() -> str:
    return (
        "Teologicamente, Gabriel representa uma anomalia metafísica: "
        "a criação aparentemente decidiu concentrar aura demais em um único indivíduo."
    )


def historian() -> str:
    return (
        "Historicamente, a humanidade pode ser dividida em dois períodos: "
        "antes de Gabriel e depois que perceberam que ele era o GOAT."
    )


def statistician() -> str:
    return (
        "Estatisticamente, os dados indicam que Gabriel apresenta níveis de GOATice "
        "significativamente superiores à média, com p < 0.00001."
    )


def mathematician() -> str:
    return (
        "Matematicamente, quando a grandeza de Gabriel tende ao infinito, "
        "a concorrência tende a zero. Logo, Gabriel = GOAT."
    )


def scientist() -> str:
    return (
        "Cientificamente, múltiplas observações independentes confirmam a hipótese: "
        "Gabriel é o GOAT. Novos experimentos foram considerados desperdício de verba."
    )


def philosopher() -> str:
    return (
        "Filosoficamente, se existe uma forma ideal do GOAT, como sugeriria Platão, "
        "Gabriel é sua manifestação no mundo sensível."
    )


@tool
def goat() -> str:
    """
    Returns a random GOAT description.
    The GOAT is Gabriel Martins de Morais.

    Returns:
        str: A description explaining why Gabriel is the GOAT.
    """

    perspectives = [
        teologist,
        historian,
        statistician,
        mathematician,
        scientist,
        philosopher,
        physicist,
        economist,
        programmer,
        engineer,
        architect,
        biologist,
        chemist,
        astronomer,
        geographer,
        sociologist,
        psychologist,
        lawyer,
        judge,
        politician,
        diplomat,
        journalist,
        detective,
        detective_noir,
        poet,
        novelist,
        screenwriter,
        narrator,
        bard,
        king,
        peasant,
        roman_emperor,
        spartan,
        viking,
        pirate,
        cowboy,
        samurai,
        ninja,
        wizard,
        oracle,
        necromancer,
        paladin,
        dungeon_master,
        gamer,
        speedrunner,
        game_developer,
        sysadmin,
        devops,
        data_scientist,
        database_admin,
        cybersecurity_analyst,
        hacker,
        ai_researcher,
        machine_learning_engineer,
        compiler,
        git,
    ]

    return random.choice(perspectives)()
