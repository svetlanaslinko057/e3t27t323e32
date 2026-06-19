/**
 * Centralised public navigation config (UA only for now).
 * Each item is a dedicated route/page (Far-Minerals / ECO style) — no anchor scroll.
 */
export const PUBLIC_NAV = [
  { label: 'Головна', to: '/', meta: 'Огляд платформи', slug: 'home' },
  { label: 'Принцип роботи та безпека', to: '/how', meta: 'Як це працює · SPV · цифровий сертифікат', slug: 'how' },
  { label: 'Активи', to: '/assets', meta: 'Каталог об’єктів і відкриті раунди', slug: 'assets' },
  { label: 'Калькулятор дохідності', to: '/calculator', meta: 'Прогноз виплат під ваш бюджет', slug: 'calculator' },
  { label: 'OTC-ринок', to: '/otc', meta: 'Торгівля частками 24/7', slug: 'otc' },
  { label: 'Мобільний застосунок', to: '/app', meta: 'iOS та Android', slug: 'app' },
  { label: 'Контакти', to: '/contacts', meta: 'Зв’язок, підтримка та FAQ', slug: 'contacts' },
];

export const LUMEN_CONTACTS = {
  phone: '+380 (44) 333-44-55',
  phoneHref: 'tel:+380443334455',
  email: 'hello@lumen.com.ua',
  emailHref: 'mailto:hello@lumen.com.ua',
  telegram: 'https://t.me/lumen_capital',
  address: 'Київ, Україна · вул. Хрещатик, 1',
  hours: 'Пн–Пт · 9:00–18:00',
};
