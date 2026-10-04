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
    you: "Você",
  },
} as const;

export type ChatTextKey = keyof (typeof TEXT)["es"];

export function ct(language: Language, key: ChatTextKey): string {
  return TEXT[language][key];
}
