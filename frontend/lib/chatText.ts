import type { Language } from "@/lib/types";

const TEXT = {
  es: {
    brand: "LATAM Bank",
    tagline: "Asistente de disputas",
    newChat: "Nueva conversación",
    cases: "Mis casos",
    logout: "Cerrar sesión",
    menu: "Abrir menú",
    closeMenu: "Cerrar menú",
    emptyTitle: "¿Qué cobro quieres revisar?",
    emptyBody: "Cuéntame qué pasó con una transacción. Reviso tu cuenta y, si hace falta, un especialista toma el caso.",
    placeholder: "Escribe tu mensaje",
    send: "Enviar mensaje",
    sending: "Enviando",
    jump: "Ir al último mensaje",
    copy: "Copiar respuesta",
    copied: "Copiado",
    typing: "El asistente está escribiendo",
    note: "Prototipo de demostración. Los datos son sintéticos y no se mueve dinero.",
    skip: "Ir al mensaje",
    theme: "Cambiar tema",
    recent: "Recientes",
    noRecent: "Tus conversaciones aparecerán aquí.",
    loadError: "No se pudo abrir la conversación.",
    demo: "Escenarios para demostración",
    demoHint: "Elige uno para completar los datos.",
    you: "Tú",
  },
  pt: {
    brand: "LATAM Bank",
    tagline: "Assistente de disputas",
    newChat: "Nova conversa",
    cases: "Meus casos",
    logout: "Sair",
    menu: "Abrir menu",
    closeMenu: "Fechar menu",
    emptyTitle: "Qual cobrança você quer revisar?",
    emptyBody: "Conte o que aconteceu com uma transação. Eu reviso sua conta e, se for preciso, um especialista assume o caso.",
    placeholder: "Escreva sua mensagem",
    send: "Enviar mensagem",
    sending: "Enviando",
    jump: "Ir para a última mensagem",
    copy: "Copiar resposta",
    copied: "Copiado",
    typing: "O assistente está escrevendo",
    note: "Protótipo de demonstração. Os dados são sintéticos e nenhum dinheiro é movimentado.",
    skip: "Ir para a mensagem",
    theme: "Mudar tema",
    recent: "Recentes",
    noRecent: "Suas conversas aparecerão aqui.",
    loadError: "Não foi possível abrir a conversa.",
    demo: "Cenários de demonstração",
    demoHint: "Escolha um para preencher os dados.",
    you: "Você",
  },
} as const;

export type ChatTextKey = keyof (typeof TEXT)["es"];

export function ct(language: Language, key: ChatTextKey): string {
  return TEXT[language][key];
}

const UUID = /\b([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;

/** A case id is a UUID. The reply keeps the full id (the model's checks need it), but the customer sees the short form the case card shows. */
export function shortCaseIds(text: string): string {
  return text.replace(UUID, (_match, head: string) => `#${head}`);
}
