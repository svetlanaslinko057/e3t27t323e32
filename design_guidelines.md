{
  "scope": {
    "section_name": "Investment Journey / Шлях від реєстрації до першої виплати",
    "goal": "Replace the flat 5-card row with a compact, premium, editorial, ‘alive’ journey block featuring tilted/overlapping cards, bracketed mono step numbers, micro-descriptions, and a distinctive progression device (arc + arrowheads). Must be theme-aware (light/dark) and coherent with existing LUMEN header/hero aesthetic.",
    "non_goals": [
      "Do not restyle other landing sections.",
      "Do not introduce a new palette beyond the provided greens/golds/cream + existing CSS variables.",
      "Do not add heavy/continuous animations; respect prefers-reduced-motion."
    ],
    "placement_context": "Sits between the category slider section and the blockchain/digital ownership section. Should visually ‘bridge’ them with a sense of progression and trust."
  },

  "brand_tokens_and_css_vars": {
    "hardcoded_brand_hex_allowed": {
      "forest": "#2E5D4F",
      "forest_dark": "#16382E",
      "forest_darker": "#0E2620",
      "gold": "#C9A961",
      "champagne": "#E5C98A",
      "cream": "#F4ECDA"
    },
    "theme_vars_to_use": {
      "background": "var(--background)",
      "foreground": "var(--foreground)",
      "card": "var(--card)",
      "border": "var(--border)",
      "muted_foreground": "var(--muted-foreground)",
      "ring": "var(--ring)"
    },
    "section_specific_css_custom_properties": {
      "where": "/app/frontend/src/pages/LandingPage.css (append; keep selectors scoped to this section only)",
      "tokens": {
        "--journey-cream": "#F4ECDA",
        "--journey-forest": "#2E5D4F",
        "--journey-gold": "#C9A961",
        "--journey-champagne": "#E5C98A",

        "--journey-surface": "color-mix(in oklab, var(--card) 92%, var(--journey-cream) 8%)",
        "--journey-surface-2": "color-mix(in oklab, var(--card) 86%, var(--journey-cream) 14%)",
        "--journey-border": "color-mix(in oklab, var(--border) 70%, var(--journey-gold) 30%)",
        "--journey-border-strong": "color-mix(in oklab, var(--border) 55%, var(--journey-gold) 45%)",

        "--journey-shadow": "0 1px 0 rgba(20,18,15,0.06), 0 14px 40px rgba(20,18,15,0.10)",
        "--journey-shadow-hover": "0 1px 0 rgba(20,18,15,0.08), 0 18px 60px rgba(20,18,15,0.14)",

        "--journey-radius": "18px",
        "--journey-radius-inner": "14px",

        "--journey-tilt-a": "-2.25deg",
        "--journey-tilt-b": "1.75deg",
        "--journey-tilt-c": "-1.25deg",

        "--journey-ease": "cubic-bezier(0.16, 1, 0.3, 1)",
        "--journey-dur": "220ms"
      },
      "notes": [
        "Use color-mix for subtle premium warmth; it stays theme-aware because it mixes with var(--card)/var(--border).",
        "If color-mix support is a concern, provide a fallback solid border using rgba + gold (see instructions_to_main_agent)."
      ]
    }
  },

  "typography": {
    "font_pairing": {
      "headings": "Existing grotesk heading classes already used on landing (keep).",
      "step_numbers": "IBM Plex Mono or JetBrains Mono (already imported in index.css).",
      "body": "Existing body font (var(--ds-font-body))."
    },
    "text_size_hierarchy": {
      "section_title_h1": "text-4xl sm:text-5xl lg:text-6xl (use existing lumen-h2 if already matches clamp)",
      "section_subtitle_h2": "text-base md:text-lg (use existing lumen-section-sub)",
      "step_title": "text-base sm:text-lg font-semibold tracking-tight",
      "step_microcopy": "text-sm leading-relaxed text-muted-foreground",
      "eyebrow": "uppercase text-[11px] tracking-[0.22em] font-semibold",
      "step_number": "font-mono text-[12px] tracking-[0.18em]"
    },
    "copy_treatment": {
      "eyebrow_example": "INVESTMENT JOURNEY / ШЛЯХ ІНВЕСТОРА",
      "badge_example": "~ 5 steps • from $1,000 • dividends in USD/USDT",
      "microcopy_rule": "Each step gets 1 crisp line (max ~90 chars). Avoid paragraphs; compact premium tone."
    }
  },

  "layout_blueprint": {
    "overall_section_container": {
      "structure": [
        "Section wrapper with max width aligned to existing landing grid.",
        "Header row: eyebrow + title + subtitle + small badge.",
        "Journey stage: overlapping tilted cards + arc connector behind them.",
        "Mobile: horizontal scroll ‘film strip’ with snap + mini progress indicator."
      ],
      "spacing_scale_compact": {
        "section_padding_y": "py-10 sm:py-12 (avoid py-20/24)",
        "header_to_cards_gap": "mt-6 sm:mt-7",
        "card_internal_padding": "p-4 sm:p-5",
        "card_gap_visual": "Use overlap (negative translate) instead of large gaps"
      },
      "grid": {
        "desktop": "12-col mental model; cards occupy a single ‘stage’ area with controlled overflow.",
        "stage_height": "~ 340–380px desktop; auto on mobile",
        "overflow": "Allow overflow-x visible on desktop for ‘bleed’ effect; clip only the arc if needed."
      }
    },

    "distinctive_stage_composition": {
      "concept": "A ‘curated stack’ of 5 cards that slightly overlap and alternate tilt, with a thin arc path behind them and small arrowheads between steps. On hover/focus, the active card straightens slightly, lifts, and its icon fills; the arc segment under it brightens to champagne.",
      "desktop_layout": {
        "implementation": "Use a relative stage container. Place cards in a CSS grid row but apply per-card transforms (rotate + translateX) to create overlap. Keep DOM order linear for accessibility.",
        "card_positions": {
          "rule": "Cards are in a flex row; each subsequent card has a negative left margin to overlap.",
          "values": {
            "base_width": "min(320px, 78vw) on mobile; 280–320px on desktop",
            "overlap": "-28px (sm), -34px (lg)",
            "tilts": "[-2.25deg, 1.75deg, -1.25deg, 2deg, -1deg]",
            "y_offsets": "[0px, 10px, -6px, 12px, 0px]"
          }
        },
        "arc_connector": {
          "type": "SVG path absolutely positioned behind cards",
          "style": "1px stroke using --journey-border; dashed subtle; glow on active segment",
          "arrowheads": "Small arrow markers at step boundaries (SVG marker-end)"
        }
      },
      "mobile_layout": {
        "pattern": "Horizontal scroll with snap + slight tilt retained; arc becomes a subtle top border line with dots.",
        "implementation": "Use ScrollArea (shadcn) or a div with overflow-x-auto + snap-x snap-mandatory + no-scrollbar.",
        "snap": "snap-start on each card; add left/right padding so first/last card center nicely.",
        "progress": "Below cards: 5-dot indicator (like your slider controls) synced to active index (IntersectionObserver or scroll position)."
      }
    }
  },

  "component_specifications": {
    "shadcn_components_to_use": {
      "badge": {
        "path": "/app/frontend/src/components/ui/badge.jsx",
        "usage": "Use for the small ‘5 steps / from $1,000’ badge in header and optional per-step tag (e.g., BANK/USDT)."
      },
      "card": {
        "path": "/app/frontend/src/components/ui/card.jsx",
        "usage": "Base semantics only; styling should be custom via LandingPage.css classes to match premium editorial look."
      },
      "tooltip": {
        "path": "/app/frontend/src/components/ui/tooltip.jsx",
        "usage": "Optional: on desktop, hover the step number to show a 1-line ‘why it matters’ tooltip. Keep minimal."
      },
      "scroll_area": {
        "path": "/app/frontend/src/components/ui/scroll-area.jsx",
        "usage": "Recommended for mobile horizontal scroll to keep scrollbars hidden and consistent."
      }
    },
    "icons": {
      "library": "lucide-react",
      "rule": "Each step uses a line icon + a filled variant simulated by layering two icons (stroke + filled) and crossfading on hover/focus.",
      "suggested_icons": {
        "step_1": "Search / Building2",
        "step_2": "CreditCard / Landmark",
        "step_3": "BadgeCheck / ShieldCheck",
        "step_4": "Coins / HandCoins",
        "step_5": "ArrowLeftRight / Repeat"
      },
      "filled_state_approach": {
        "method": "Use two SVGs: outline icon always visible; ‘filled’ look achieved by a second icon with thicker stroke + background disk + mask, or by using a solid circle behind and changing stroke color to forest.",
        "note": "Lucide is outline-only; do not hunt for a different icon set. Simulate fill with background + stroke swap + subtle inner shadow."
      }
    }
  },

  "interaction_and_motion_choreography": {
    "scroll_reveal": {
      "library": "framer-motion v12",
      "trigger": "whileInView with viewport once:true amount:0.35",
      "sequence": [
        "Section header fades in + rises 10px.",
        "Arc path draws in (stroke-dashoffset animation) after 120ms.",
        "Cards reveal with stagger: each card rises 14px, rotates from 0deg to its tilt, opacity 0→1.",
        "Arrowheads fade in last (subtle)."
      ],
      "timings": {
        "header": "duration 0.55s ease [0.16,1,0.3,1]",
        "arc_draw": "duration 0.9s ease [0.16,1,0.3,1]",
        "card": "duration 0.5s each, stagger 0.08s",
        "reduced_motion": "If prefers-reduced-motion: skip arc draw + rotation; only opacity."
      }
    },

    "hover_focus_states": {
      "card_hover": {
        "effects": [
          "Lift: translateY(-4px)",
          "Straighten slightly: rotate toward 0deg by ~1deg",
          "Border: --journey-border → --journey-border-strong",
          "Shadow: --journey-shadow → --journey-shadow-hover",
          "Icon disk: cream→champagne tint",
          "Step number bracket: gold becomes stronger"
        ],
        "transition": "transition: box-shadow var(--journey-dur) var(--journey-ease), border-color var(--journey-dur) var(--journey-ease), background-color var(--journey-dur) var(--journey-ease) (NO transition: all)"
      },
      "icon_swap": {
        "pattern": "Two layers: .icon-outline (opacity 1) and .icon-active (opacity 0). On hover/focus-within: crossfade (outline 1→0.15, active 0→1) + slight scale 1→1.04.",
        "duration": "160–200ms"
      },
      "connector_reaction": {
        "pattern": "On hover of card i: highlight arc segment under i (stroke color to champagne, add subtle glow via filter: drop-shadow).",
        "implementation_hint": "Maintain activeIndex in React state on mouseenter/focus; pass to SVG to set classnames per segment."
      }
    },

    "micro_interactions": {
      "cursor": "Keep default cursor; cards are interactive only if they have a click action. If no click, still allow hover but do not show pointer cursor.",
      "press": "If cards become clickable (e.g., jump to section): active scale 0.99 and translateY(-2px).",
      "keyboard": "Each card container should be focusable only if interactive (tabIndex=0). Focus ring uses existing .focus-ring utility or custom ring with --journey-gold."
    }
  },

  "content_structure": {
    "header_block": {
      "elements": [
        "Eyebrow (uppercase, wide tracking)",
        "Title (existing lumen-h2)",
        "Subtitle (existing lumen-section-sub)",
        "Badge (shadcn Badge)"
      ],
      "badge_style": "Outline badge with border mixed with gold; background transparent; in dark theme use slightly elevated surface."
    },

    "step_card_anatomy": {
      "top_row": [
        "[ 01 ] mono bracket number",
        "Optional mini-tag badge (e.g., BANK / USDT) aligned right"
      ],
      "main": [
        "Icon disk (32–36px) with icon",
        "Step title (UK/EN bilingual line or toggle-aware)",
        "Micro-description (1 line)"
      ],
      "footer": [
        "A tiny ‘progress cue’ (arrow glyph or ‘Next’ label) only on desktop; hide on mobile to reduce clutter"
      ]
    },

    "microcopy_per_step_en": {
      "1": "Browse open objects — each with its own economics.",
      "2": "Pay by bank or USDT; sign with digital signature.",
      "3": "Receive an on-chain NFT certificate of ownership.",
      "4": "Earn dividends proportional to your share (monthly/quarterly).",
      "5": "Exit via LUMEN’s secondary OTC market when you choose."
    },
    "microcopy_per_step_uk": {
      "1": "Переглядаєте об’єкти — кожен має власну економіку.",
      "2": "Оплата банк/USDT; підпис через ЕЦП.",
      "3": "NFT-сертифікат фіксує право власності on-chain.",
      "4": "Дивіденди пропорційно частці (щомісяця/квартал).",
      "5": "Вихід через вторинний OTC-ринок LUMEN у будь-який момент."
    }
  },

  "implementation_notes_react_js": {
    "file_targets": {
      "react_section_component": "Wherever the landing sections live (likely /app/frontend/src/pages/LandingPage.jsx). Create a dedicated component e.g., InvestmentJourneySection.jsx (JS, not TS) and import it.",
      "css": "/app/frontend/src/pages/LandingPage.css (append new scoped classes)"
    },
    "recommended_dom_structure": {
      "outline": [
        "<section data-testid=\"investment-journey-section\" className=\"lumen-journey\">",
        "  <div className=\"lumen-journey__inner\">",
        "    <header className=\"lumen-journey__header\"> ... </header>",
        "    <div className=\"lumen-journey__stage\">",
        "      <JourneyArcSvg activeIndex={activeIndex} />",
        "      <div className=\"lumen-journey__cards\" role=\"list\">",
        "        {steps.map((s,i)=> (",
        "          <motion.article role=\"listitem\" data-testid=\"investment-journey-step-card\" ...> ... </motion.article>",
        "        ))}",
        "      </div>",
        "      <MobileDots data-testid=\"investment-journey-dots\" ... />",
        "    </div>",
        "  </div>",
        "</section>"
      ]
    },
    "data_testid_requirements": {
      "section": "investment-journey-section",
      "badge": "investment-journey-badge",
      "card": "investment-journey-step-card-{index}",
      "card_title": "investment-journey-step-title-{index}",
      "card_desc": "investment-journey-step-desc-{index}",
      "dots": "investment-journey-progress-dots",
      "dot": "investment-journey-progress-dot-{index}"
    },
    "active_index_logic": {
      "desktop": "Set activeIndex on onMouseEnter/onFocus for each card; clear on mouseleave (optional keep last).",
      "mobile": "Use IntersectionObserver on scroll container to set activeIndex based on most-visible card; or compute from scrollLeft / cardWidth."
    },
    "svg_arc_details": {
      "approach": "Render one path per segment (5 segments) so you can highlight the active segment. Use stroke-dasharray animation for reveal.",
      "accessibility": "SVG is decorative: aria-hidden=\"true\" focusable=\"false\""
    },
    "reduced_motion": {
      "how": "Use useReducedMotion() from framer-motion; if true, disable rotate/translate animations and arc draw; keep opacity only."
    }
  },

  "css_class_blueprint": {
    "section_classes": {
      ".lumen-journey": "py-10 sm:py-12",
      ".lumen-journey__inner": "mx-auto max-w-6xl px-4 sm:px-6",
      ".lumen-journey__header": "flex flex-col gap-3",
      ".lumen-journey__kicker": "text-[11px] font-semibold tracking-[0.22em] uppercase text-muted-foreground",
      ".lumen-journey__title": "(use existing lumen-h2 class)",
      ".lumen-journey__sub": "(use existing lumen-section-sub class)",
      ".lumen-journey__badge": "inline-flex w-fit"
    },
    "stage_and_cards": {
      ".lumen-journey__stage": "relative mt-6 sm:mt-7",
      ".lumen-journey__arc": "absolute inset-x-0 top-6 h-[220px] pointer-events-none",
      ".lumen-journey__cards": "relative flex gap-0 overflow-visible",
      ".lumen-journey__cards--desktop": "hidden lg:flex",
      ".lumen-journey__cards--mobile": "lg:hidden"
    },
    "card_style": {
      ".journey-card": "relative w-[78vw] max-w-[340px] sm:w-[320px] rounded-[var(--journey-radius)] border bg-[var(--journey-surface)] shadow-[var(--journey-shadow)]",
      ".journey-card__inner": "rounded-[var(--journey-radius-inner)] p-4 sm:p-5",
      ".journey-card + .journey-card": "ml-[-28px] sm:ml-[-28px] lg:ml-[-34px]",
      ".journey-card:hover": "border-color: var(--journey-border-strong); box-shadow: var(--journey-shadow-hover)",
      ".journey-card:focus-within": "box-shadow: 0 0 0 2px var(--background), 0 0 0 4px var(--journey-gold), var(--journey-shadow-hover)"
    },
    "card_top_row": {
      ".journey-card__top": "flex items-center justify-between gap-3",
      ".journey-card__num": "font-mono text-[12px] tracking-[0.18em] text-[color:var(--muted-foreground)]",
      ".journey-card__num strong": "color: var(--journey-gold); font-weight: 600"
    },
    "icon_disk": {
      ".journey-card__iconWrap": "mt-4 inline-flex h-9 w-9 items-center justify-center rounded-full border",
      "disk_bg": "background: color-mix(in oklab, var(--journey-cream) 55%, transparent);",
      "disk_border": "border-color: color-mix(in oklab, var(--journey-border) 70%, transparent);",
      "hover": "On hover/focus: background shifts toward champagne; border strengthens"
    },
    "title_and_desc": {
      ".journey-card__title": "mt-3 text-base sm:text-lg font-semibold tracking-tight",
      ".journey-card__desc": "mt-1 text-sm leading-relaxed text-muted-foreground"
    },
    "no_transition_all_rule": "Do not use transition: all anywhere in this section."
  },

  "progression_device_variants": {
    "primary_recommended": {
      "name": "Arc + arrowheads behind overlapping cards",
      "why": "Feels bespoke and ‘flow/progression’ without adding vertical whitespace. Works with your existing split-slider vibe.",
      "desktop": "Arc visible behind cards; segments highlight on hover.",
      "mobile": "Arc simplified to a thin line + dots under the scroll strip."
    },
    "alternative": {
      "name": "Circular ‘orbit’ mini-map",
      "description": "A small circular diagram (top-right of stage) with 5 ticks; active tick highlights with gold. Cards remain the main content.",
      "note": "Only add if client wants extra ‘alive’ detail; keep subtle to avoid gimmick."
    }
  },

  "accessibility": {
    "contrast": [
      "Ensure step titles meet WCAG AA against card surface in both themes.",
      "Gold is accent only; do not use gold for long text."
    ],
    "focus": "Visible focus ring on any interactive card/button. Use :focus-visible where possible.",
    "reduced_motion": "Respect prefers-reduced-motion: remove arc draw + rotation; keep opacity only.",
    "semantics": "Use role=list/listitem or <ol><li> for steps; keep reading order 1→5."
  },

  "performance": {
    "rules": [
      "SVG arc is lightweight; avoid filters that are too heavy. If using drop-shadow, keep blur <= 8.",
      "Avoid continuous animations; only in-view reveal + hover.",
      "Use will-change sparingly (only on hovered card)."
    ]
  },

  "image_urls": {
    "note": "No new imagery required for this section; it should be typographic + icon-driven to stay premium and coherent with LUMEN."
  },

  "component_path": {
    "shadcn_ui": [
      "/app/frontend/src/components/ui/badge.jsx",
      "/app/frontend/src/components/ui/card.jsx",
      "/app/frontend/src/components/ui/scroll-area.jsx",
      "/app/frontend/src/components/ui/tooltip.jsx"
    ],
    "css": [
      "/app/frontend/src/pages/LandingPage.css"
    ]
  },

  "instructions_to_main_agent": [
    "Implement as a new React (JS) component (e.g., InvestmentJourneySection.jsx) and swap it into LandingPage.jsx where the old flat row exists.",
    "Append scoped CSS to LandingPage.css using the class blueprint above; do not touch global tokens in index.css.",
    "Use framer-motion v12 for in-view reveal + stagger; use useReducedMotion() to disable rotation/arc draw.",
    "Create an SVG arc behind cards with 5 segments; highlight segment based on activeIndex (hover/focus/scroll).",
    "Cards must be compact: section py-10/12, header-to-cards mt-6/7, card padding p-4/5. Avoid large vertical gaps.",
    "Do NOT use generic icon fill libraries; simulate ‘filled’ state via background disk + stroke color swap + layered icon opacity.",
    "All interactive/key elements must include data-testid attributes as specified.",
    "Fallback for color-mix: if needed, replace --journey-border with rgba(201,169,97,0.35) and --journey-border-strong with rgba(201,169,97,0.55)."
  ],

  "appendix_general_ui_ux_design_guidelines": "<General UI UX Design Guidelines>  \n    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n</General UI UX Design Guidelines>"
}
