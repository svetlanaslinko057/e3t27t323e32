{
  "brand": {
    "name": "LUMEN",
    "visual_personality": {
      "attributes": [
        "преміальний",
        "bank‑grade довіра",
        "стриманий модерн",
        "редакційний (editorial) ритм",
        "тактильний (теплий папір + темний лісовий зелений)",
        "інженерна точність у деталях"
      ],
      "do_not": [
        "Не робити сайт як один довгий лендінг із якорями — кожен пункт меню має бути окремою сторінкою/URL.",
        "Не дублювати глибокий контент підсторінок на головній — головна лише продає (тизери + CTA).",
        "Не ламати існуючі /otc та /app — лише обгорнути в PublicLayout і стилістично вирівняти хедер/футер.",
        "Не вводити нову палітру — використовуємо поточні LUMEN CSS vars та lumen-* утиліти."
      ]
    },
    "language": "uk-UA"
  },

  "design_tokens": {
    "note": "КОЛЬОРИ НЕ ЗМІНЮЄМО. Нижче — лише нормалізація використання існуючих змінних/класів. Якщо у проєкті вже є --t-bg/--t-text-primary/--t-signal/--t-surface — використовувати їх як джерело правди.",
    "palette_fixed": {
      "primary_deep_green": "#2E5D4F",
      "very_dark_green": "#062614",
      "cream": "#FBF9F4",
      "white": "#FFFFFF",
      "warm_beige_border": "#E6E1D6",
      "gold_accent": "(існуючий gold/champagne accent у hero highlight words — НЕ міняти, лише застосовувати точково)"
    },
    "css_vars_to_use": {
      "background": "var(--t-bg)",
      "surface": "var(--t-surface)",
      "text_primary": "var(--t-text-primary)",
      "text_secondary": "var(--t-text-secondary)",
      "border": "var(--t-border, var(--token-border))",
      "signal_green": "var(--t-signal)",
      "signal_green_soft": "var(--t-signal-bg-soft)",
      "focus_ring": "var(--token-primary)"
    },
    "typography": {
      "fonts": {
        "headings": "Space Grotesk (вже підключено в index.css)",
        "body": "Inter (вже підключено)",
        "mono": "JetBrains Mono або IBM Plex Mono (вже підключено)"
      },
      "scale_tailwind": {
        "h1": "text-4xl sm:text-5xl lg:text-6xl",
        "h2": "text-base md:text-lg",
        "body": "text-sm md:text-base",
        "small": "text-xs md:text-sm"
      },
      "editorial_rules": [
        "H1 завжди короткий (до 7–9 слів), з великим трекінгом лише у кікерах/лейблах.",
        "Breadcrumb — дрібний, моно або uppercase, завжди вище H1.",
        "Для цифр/відсотків у статах — tabular-nums (вже є в body font-variant-numeric)."
      ]
    },
    "radius_shadow_spacing": {
      "radius": {
        "card": "rounded-2xl (або 16px)",
        "button": "rounded-xl (10–12px)",
        "pill_badge": "rounded-full"
      },
      "shadows": {
        "card": "використовувати існуючі token shadows (var(--token-shadow-card)/hover) або дуже м’які тіні на світлому фоні",
        "dark_sections": "на темному фоні тіні мінімізувати, працювати контрастом і бордерами"
      },
      "layout_spacing": {
        "section_py": "py-14 md:py-20",
        "container": "max-w-6xl xl:max-w-7xl px-4 sm:px-6 lg:px-8",
        "grid_gap": "gap-6 md:gap-8",
        "rule": "Використовувати 2–3× більше повітря, ніж здається потрібним."
      }
    },
    "motion": {
      "easing": {
        "standard": "[0.16, 1, 0.3, 1]",
        "exit": "[0.7, 0, 0.84, 0]"
      },
      "durations_ms": {
        "menu_overlay_in": 520,
        "menu_overlay_out": 380,
        "stagger": 70,
        "section_reveal": 520,
        "page_curtain": 520
      },
      "reduced_motion": {
        "rule": "Поважати prefers-reduced-motion: прибрати паралакс/стагер, залишити лише opacity без зсувів."
      }
    }
  },

  "layout_system": {
    "public_shell": {
      "name": "PublicLayout",
      "structure": [
        "Header (sticky, прозорий/blur на світлому; на темному — напівпрозорий)",
        "Route content (Outlet)",
        "FooterMega (гігантський wordmark фон + колонки)",
        "OverlayMenu (портал поверх усього)",
        "PageTransitionCurtain (між роутами)"
      ],
      "header_constraints": {
        "left": "Анімований тригер 'МЕНЮ' з емблемою-астериском: hover rotate 12°, open -> rotate 45° + morph у X/‘Закрити’.",
        "center": "Лого LUMEN (клік -> /)",
        "right": "Телефон + Primary CTA 'Замовити дзвінок' + кнопка 'Кабінет/Увійти'"
      },
      "grid": {
        "desktop": "12 колонок; контент 8–10 колонок по центру; праві/ліві декоративні поля для лейблів",
        "mobile": "1 колонка; CTA завжди видимий; меню тригер зліва не зникає"
      }
    },
    "page_hero": {
      "pattern": "Темний hero (very_dark_green) з breadcrumb + display title + короткий підзаголовок + 1–2 CTA.",
      "breadcrumb_example": "ГОЛОВНА • КОНТАКТИ",
      "title_style": "Space Grotesk, tracking-tight, leading-[0.95], max-w-[14ch]",
      "background_detail": "Ледь помітний grain/noise overlay + великий watermark 'LUMEN' або 'INVEST' на 3–6% opacity (НЕ градієнт)."
    }
  },

  "navigation_overlay_menu": {
    "interaction_spec": {
      "open": [
        "Клік по тригеру зліва відкриває full-screen overlay.",
        "Overlay має dim scrim + великий watermark логотип по центру/внизу.",
        "Лінки з’являються staggered (знизу вгору) з легким blur->sharp.",
        "Фокус-трап всередині меню; ESC закриває; клік по scrim закриває."
      ],
      "close": [
        "Закриття — reverse stagger (staggerDirection:-1).",
        "Тригер повертається у 'МЕНЮ' з коротким overshoot-rotate."
      ],
      "menu_items": [
        {"label":"Головна","to":"/"},
        {"label":"Принцип роботи та безпека","to":"/how"},
        {"label":"Активи","to":"/assets"},
        {"label":"Калькулятор","to":"/calculator"},
        {"label":"Контакти","to":"/contacts"},
        {"label":"OTC-ринок","to":"/otc"},
        {"label":"Мобільний застосунок","to":"/app"}
      ],
      "framer_motion_variants_js": {
        "overlay": "const overlayV = { hidden:{opacity:0}, show:{opacity:1, transition:{duration:0.52, ease:[0.16,1,0.3,1], when:'beforeChildren'}}, exit:{opacity:0, transition:{duration:0.38, ease:[0.7,0,0.84,0]}} }",
        "panel": "const panelV = { hidden:{y:-24, opacity:0}, show:{y:0, opacity:1, transition:{duration:0.52, ease:[0.16,1,0.3,1]}}, exit:{y:-16, opacity:0, transition:{duration:0.32, ease:[0.7,0,0.84,0]}} }",
        "list": "const listV = { hidden:{}, show:{transition:{staggerChildren:0.07, delayChildren:0.12}}, exit:{transition:{staggerChildren:0.05, staggerDirection:-1}} }",
        "item": "const itemV = { hidden:{opacity:0, y:18, filter:'blur(6px)'}, show:{opacity:1, y:0, filter:'blur(0px)', transition:{duration:0.32, ease:[0.16,1,0.3,1]}}, exit:{opacity:0, y:10, filter:'blur(4px)', transition:{duration:0.22, ease:[0.7,0,0.84,0]}} }"
      },
      "tailwind_class_recipe": {
        "overlay_root": "fixed inset-0 z-[100] bg-[rgba(6,38,20,0.86)] backdrop-blur-md",
        "watermark": "pointer-events-none absolute inset-0 flex items-end justify-center pb-10 text-[18vw] font-semibold tracking-tight text-white/5",
        "menu_container": "relative h-full w-full",
        "menu_grid": "mx-auto flex h-full max-w-7xl flex-col justify-between px-4 py-6 sm:px-6 lg:px-8",
        "links": "mt-10 space-y-3",
        "link": "group inline-flex items-baseline gap-3 text-3xl sm:text-4xl lg:text-5xl font-medium text-[var(--t-bg)]",
        "link_meta": "text-xs font-mono tracking-[0.18em] text-white/60 group-hover:text-white/80"
      },
      "testing": {
        "data_testids": {
          "trigger": "public-menu-trigger",
          "overlay": "public-menu-overlay",
          "close": "public-menu-close",
          "nav_link": "public-menu-link-<slug>"
        }
      }
    }
  },

  "page_transition": {
    "pattern": "Curtain wipe між роутами (не на скролі).",
    "implementation_hint_js": {
      "component": "PublicRouteTransition.jsx (AnimatePresence mode='wait')",
      "variant": "const curtainV={initial:{scaleY:0, transformOrigin:'top'}, animate:{scaleY:0}, exit:{scaleY:1, transition:{duration:0.52, ease:[0.16,1,0.3,1]}}}"
    },
    "rule": "Curtain має бути однотонний (very_dark_green) без градієнтів."
  },

  "reusable_primitives": {
    "components": [
      {
        "name": "PageHero",
        "purpose": "Єдиний стиль hero для всіх публічних сторінок: breadcrumb + H1 + lead + CTA.",
        "data_testids": ["page-hero", "page-hero-breadcrumb", "page-hero-title", "page-hero-primary-cta"]
      },
      {
        "name": "Reveal",
        "purpose": "Scroll-reveal wrapper (useInView) для кожної секції/карти.",
        "data_testids": ["reveal"]
      },
      {
        "name": "SectionLabel",
        "purpose": "Кікер/лейбл секції (моно/uppercase) + тонка лінія separator.",
        "data_testids": ["section-label"]
      },
      {
        "name": "StatCard",
        "purpose": "Довіра/метрики (AUM, виплати, активи, середня дохідність).",
        "data_testids": ["stat-card"]
      },
      {
        "name": "AssetCard",
        "purpose": "Картка активу: назва, локація, yield %, ціна від, прогрес раунду (Progress).",
        "data_testids": ["asset-card", "asset-card-progress"]
      },
      {
        "name": "FooterMega",
        "purpose": "Гігантський футер з wordmark фоном + колонки + bottom bar.",
        "data_testids": ["footer-mega", "footer-newsletter-form", "footer-cta"]
      }
    ]
  },

  "pages_blueprints": {
    "home": {
      "route": "/",
      "goal": "Продати і направити в /assets або /how або /contacts. Мінімум дублювання.",
      "sections": [
        {
          "name": "HeroSell",
          "content": {
            "h1": "Інвестуйте в реальні активи від $1,000",
            "lead": "Доступ до часткової участі в об’єктах із прозорою структурою власності та зрозумілою моделлю виплат.",
            "cta_primary": "Переглянути активи",
            "cta_secondary": "Як це працює"
          }
        },
        {
          "name": "OpenRoundsTeaser",
          "content": {
            "label": "АКТИВИ У ВІДКРИТИХ РАУНДАХ",
            "note": "Показати 3–6 карток AssetCard + кнопка 'Усі активи'."
          }
        },
        {
          "name": "TrustStats",
          "content": {
            "stats": ["Виплати інвесторам", "Активи на платформі", "Середня дохідність", "Середній термін"]
          }
        },
        {
          "name": "TeaserBlocks",
          "content": {
            "items": [
              {"title":"Принцип роботи","desc":"4 кроки від вибору активу до виходу через OTC.","to":"/how"},
              {"title":"Безпека та власність","desc":"Юридична структура, ескроу, цифровий сертифікат.","to":"/how"},
              {"title":"Калькулятор","desc":"Оцініть прогноз виплат під ваш бюджет.","to":"/calculator"}
            ]
          }
        },
        {
          "name": "NewsTicker",
          "content": {
            "pattern": "Горизонтальний marquee/scroll-area з короткими новинами/оновленнями (без автоскролу при reduced-motion)."
          }
        },
        {
          "name": "FinalCTA",
          "content": {
            "title": "Готові почати з першого активу?",
            "cta": "Отримати консультацію"
          }
        }
      ]
    },

    "how_it_works": {
      "route": "/how",
      "goal": "Довга редакційна сторінка з плавним скролом і reveal-анімаціями.",
      "sections": [
        {"name":"Hero","content":{"breadcrumb":"ГОЛОВНА • ПРИНЦИП РОБОТИ","title":"Як працює LUMEN","lead":"Від вибору активу до виплат і виходу — прозоро, поетапно, з фіксацією прав."}},
        {"name":"4Steps","content":{"steps":["Обираєте актив і суму","Отримуєте цифровий сертифікат","Щомісячні виплати","Вихід через OTC або завершення терміну"]}},
        {"name":"SecurityEditorial","content":{"topics":["SPV/структура володіння","Ескроу/розрахунки","Юридичні документи","Докази/реєстри/цифровий слід"]}},
        {"name":"FAQTeaser","content":{"cta":"Перейти до контактів","to":"/contacts"}}
      ]
    },

    "assets": {
      "route": "/assets",
      "goal": "Каталог активів з фільтрами та live прогресом раундів.",
      "sections": [
        {"name":"Hero","content":{"title":"Активи","lead":"Обирайте об’єкти з відкритими раундами та прозорими параметрами."}},
        {"name":"Filters","content":{"pattern":"Tabs/Select + search; sticky на мобільному при скролі."}},
        {"name":"Grid","content":{"pattern":"AssetCard grid 1col mobile / 2col md / 3col xl"}}
      ]
    },

    "calculator": {
      "route": "/calculator",
      "goal": "Швидко показати прогноз виплат і підштовхнути до вибору активу.",
      "sections": [
        {"name":"Hero","content":{"title":"Калькулятор дохідності","lead":"Оцініть прогноз виплат на основі суми, терміну та параметрів активу."}},
        {"name":"CalculatorCard","content":{"inputs":["Сума інвестиції","Актив","Термін"],"outputs":["Щомісячна виплата","Річна дохідність","Загальний результат"],"note":"Пояснення припущень дрібним текстом."}}
      ]
    },

    "contacts": {
      "route": "/contacts",
      "goal": "Преміальна контактна сторінка: канали, копіювання, форма, FAQ.",
      "sections": [
        {"name":"Hero","content":{"breadcrumb":"ГОЛОВНА • КОНТАКТИ","title":"Контакти","lead":"Поставте запитання менеджеру або залиште заявку — відповімо у робочий час."}},
        {"name":"DirectChannels","content":{"items":["Телефон","Email","Telegram"],"features":["Copy button","Live indicator 'менеджер на лінії'"]}},
        {"name":"QuickRequestForm","content":{"fields":["Ім’я","Телефон","Тема","Повідомлення"],"cta":"Замовити дзвінок"}},
        {"name":"FAQ","content":{"pattern":"Accordion (shadcn) з 8–12 питаннями"}}
      ]
    }
  },

  "footer_mega": {
    "structure": {
      "top": [
        "Brand block: лого + короткий слоган + CTA",
        "Link columns: Компанія / Інвестору / Продукти / Документи",
        "Contacts: телефон, email, месенджери",
        "Newsletter: email input + submit"
      ],
      "background_wordmark": "Величезний 'LUMEN' як фон (text-white/5 на темному або text-[very_dark_green]/[0.06] на світлому).",
      "bottom_bar": ["© LUMEN, рік", "Політика конфіденційності", "Умови", "Badges/позначки"]
    },
    "tailwind_recipe": {
      "root": "relative overflow-hidden bg-[var(--t-signal)] text-[var(--t-bg)]",
      "inner": "mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8",
      "grid": "grid gap-10 md:grid-cols-12",
      "wordmark": "pointer-events-none absolute inset-x-0 bottom-[-0.15em] text-center text-[22vw] font-semibold tracking-tight text-white/5"
    }
  },

  "shadcn_components_to_use": {
    "component_path": {
      "Button": "/app/frontend/src/components/ui/button.jsx",
      "Sheet": "/app/frontend/src/components/ui/sheet.jsx",
      "Dialog": "/app/frontend/src/components/ui/dialog.jsx",
      "Accordion": "/app/frontend/src/components/ui/accordion.jsx",
      "Breadcrumb": "/app/frontend/src/components/ui/breadcrumb.jsx",
      "Tabs": "/app/frontend/src/components/ui/tabs.jsx",
      "Select": "/app/frontend/src/components/ui/select.jsx",
      "Progress": "/app/frontend/src/components/ui/progress.jsx",
      "Slider": "/app/frontend/src/components/ui/slider.jsx",
      "Input": "/app/frontend/src/components/ui/input.jsx",
      "Textarea": "/app/frontend/src/components/ui/textarea.jsx",
      "Card": "/app/frontend/src/components/ui/card.jsx",
      "ScrollArea": "/app/frontend/src/components/ui/scroll-area.jsx",
      "Sonner": "/app/frontend/src/components/ui/sonner.jsx"
    },
    "rule": "Не використовувати нативні HTML dropdown/calendar/toast — тільки shadcn компоненти з /components/ui."
  },

  "libraries": {
    "already_installed": ["framer-motion", "react-router-dom@7", "lucide-react", "tailwindcss", "shadcn/ui"],
    "optional": [
      {
        "name": "@uidotdev/usehooks (optional)",
        "why": "зручні хуки для copy-to-clipboard/lock-body-scroll (можна і без залежності)",
        "install": "npm i @uidotdev/usehooks",
        "usage": "Використати для копіювання контактів або блокування скролу при відкритому меню."
      }
    ]
  },

  "image_urls": {
    "hero_backgrounds": [
      {
        "url": "https://images.unsplash.com/photo-1664565241519-292a1a0b8886?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MTJ8MHwxfHNlYXJjaHwzfHxwcmVtaXVtJTIwcmVhbCUyMGVzdGF0ZSUyMGJ1aWxkaW5nJTIwZmFjYWRlJTIwbWluaW1hbHxlbnwwfHx8Z3JlZW58MTc4MTg2MzM2Mnww&ixlib=rb-4.1.0&q=85",
        "category": "home-hero",
        "description": "Преміальна архітектура (абстрактний фасад) — використовувати як дуже затемнений фон у hero (opacity 10–18%)."
      }
    ],
    "assets_placeholders": [
      {
        "url": "https://images.pexels.com/photos/15408878/pexels-photo-15408878.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "asset-card",
        "description": "Фасад/геометрія — як плейсхолдер для активів без фото (з кропом 16:9)."
      }
    ]
  },

  "accessibility": {
    "requirements": [
      "Фокус-стили: видимий ring (не прибирати outline без заміни).",
      "Overlay menu: aria-modal, role='dialog' або nav + focus trap; ESC close.",
      "Контраст: на темному фоні текст тільки світлий; на світлому — тільки темний (без напівпрозорих дрібних текстів нижче 60%).",
      "Reduced motion: вимикати паралакс/стагер/маркі; залишати прості fade-in."
    ]
  },

  "testing": {
    "data_testid_rule": "Усі інтерактивні та ключові інформативні елементи мають data-testid у kebab-case (роль, не вигляд).",
    "examples": [
      "data-testid='header-menu-trigger'",
      "data-testid='header-primary-cta-button'",
      "data-testid='assets-filter-category-tabs'",
      "data-testid='calculator-invest-amount-input'",
      "data-testid='contacts-copy-phone-button'",
      "data-testid='footer-newsletter-submit-button'"
    ]
  },

  "instructions_to_main_agent": {
    "routing": [
      "Перевести публічну частину на react-router-dom v7 routes: /, /how, /assets, /calculator, /contacts, /otc, /app.",
      "Зробити PublicLayout з Outlet і обгорнути /otc та /app, не змінюючи їх бізнес-логіку.",
      "Меню: кожен пункт веде на URL, без anchor scroll."
    ],
    "css_strategy": [
      "Не чіпати існуючі CSS vars палітри. Додати нові класи лише з префіксом lpub- (наприклад lpub-hero, lpub-footer).",
      "Не використовувати transition: all (див. загальні правила нижче).",
      "Не центрувати контейнер глобально (не додавати .App { text-align:center })."
    ],
    "performance": [
      "Lazy-load важкі сторінки (/assets, /calculator) через React.lazy + Suspense.",
      "Анімації тільки transform/opacity; уникати layout thrash.",
      "useInView threshold 0.2–0.3; once:true для секцій." 
    ]
  }
}

---

<General UI UX Design Guidelines>  
    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms
    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text
   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json

 **GRADIENT RESTRICTION RULE**
NEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc
NEVER use dark gradients for logo, testimonial, footer etc
NEVER let gradients cover more than 20% of the viewport.
NEVER apply gradients to text-heavy content or reading areas.
NEVER use gradients on small UI elements (<100px width).
NEVER stack multiple gradient layers in the same viewport.

**ENFORCEMENT RULE:**
    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors

**How and where to use:**
   • Section backgrounds (not content backgrounds)
   • Hero section header content. Eg: dark to light to dark color
   • Decorative overlays and accent elements only
   • Hero section with 2-3 mild color
   • Gradients creation can be done for any angle say horizontal, vertical or diagonal

- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**

</Font Guidelines>

- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. 
   
- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.

- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.
   
- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly
    Eg: - if it implies playful/energetic, choose a colorful scheme
           - if it implies monochrome/minimal, choose a black–white/neutral scheme

**Component Reuse:**
	- Prioritize using pre-existing components from src/components/ui when applicable
	- Create new components that match the style and conventions of existing components when needed
	- Examine existing components to understand the project's component patterns before creating new ones

**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component

**Best Practices:**
	- Use Shadcn/UI as the primary component library for consistency and accessibility
	- Import path: ./components/[component-name]

**Export Conventions:**
	- Components MUST use named exports (export const ComponentName = ...)
	- Pages MUST use default exports (export default function PageName() {...})

**Toasts:**
  - Use `sonner` for toasts"
  - Sonner component are located in `/app/src/components/ui/sonner.tsx`

Use 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.
</General UI UX Design Guidelines>
