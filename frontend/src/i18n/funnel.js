/**
 * i18n strings for the Investor Funnel Analytics (F1) dashboard.
 * Each key has UA + EN variants. Bound via funding.js loader.
 */
export const FUNNEL_I18N_UK = {
  'funnel.title':                'Воронка інвестора',
  'funnel.subtitle':             'Операційний граф проходження інвестора. 13 етапів, конверсії, медіани, вузькі місця.',
  'funnel.eyebrow':              'LUMEN · Аналітика',

  'funnel.range.7d':             '7 днів',
  'funnel.range.30d':            '30 днів',
  'funnel.range.90d':            '90 днів',
  'funnel.range.ytd':            'З початку року',
  'funnel.range.all':            'За весь час',

  'funnel.refresh':              'Оновити',
  'funnel.empty':                'Поки немає даних для побудови воронки за цей період.',
  'funnel.loading':              'Завантаження...',

  'funnel.kpi.investors':        'Інвесторів у вікні',
  'funnel.kpi.active':           'Активних',
  'funnel.kpi.bottleneck':       'Найповільніший етап',
  'funnel.kpi.dropoff':          'Найбільший провал',
  'funnel.kpi.none':             'Немає',

  'funnel.section.stages':       'Етапи · Кількість + конверсія',
  'funnel.section.conversion':   'Матриця конверсій',
  'funnel.section.bottlenecks':  'Вузькі місця',
  'funnel.section.durations':    'Тривалість переходів',
  'funnel.section.manager':      'Атрибуція менеджерам',
  'funnel.section.funding':      'Атрибуція по фінансуванню',
  'funnel.section.executive':    'Підсумок',

  'funnel.col.stage':            'Етап',
  'funnel.col.count':            'Кількість',
  'funnel.col.conv_prev':        'Конверсія з попереднього',
  'funnel.col.conv_start':       'Конверсія від старту',
  'funnel.col.median_prev':      'Медіана з попереднього',
  'funnel.col.median_start':     'Медіана від старту',
  'funnel.col.flags':            'Прапорці',

  'funnel.col.manager':          'Менеджер',
  'funnel.col.leads':            'Ліди',
  'funnel.col.kyc':              'KYC',
  'funnel.col.signed':           'Підписано',
  'funnel.col.funded':           'Профінансовано',
  'funnel.col.certs':            'Сертифікати',
  'funnel.col.active':           'Активні',
  'funnel.col.lead_to_funded':   'Лід → Фондовано',
  'funnel.col.volume':           'Об\'єм SEPA, €',
  'funnel.col.transfers':        'Переказів',
  'funnel.col.cert_value':       'Сертифікати, $',

  'funnel.flag.bottleneck':      'Вузьке місце',
  'funnel.flag.dropoff':         'Провал',
  'funnel.flag.none':            '—',

  'funnel.unassigned':           '— Без менеджера',
  'funnel.no_data':              'Немає даних',

  'funnel.executive.text': (active, total, bottleneck, dropoff) =>
    `${active} активних з ${total} інвесторів. Вузьке місце: ${bottleneck || '—'}. Найбільший провал: ${dropoff || '—'}.`,

  'nav.funnel':                  'Воронка інвестора',
};

export const FUNNEL_I18N_EN = {
  'funnel.title':                'Investor Funnel',
  'funnel.subtitle':             'Operational graph of an investor\'s journey through LUMEN. 13 stages, conversions, medians, bottlenecks.',
  'funnel.eyebrow':              'LUMEN · Analytics',

  'funnel.range.7d':             '7 days',
  'funnel.range.30d':            '30 days',
  'funnel.range.90d':            '90 days',
  'funnel.range.ytd':            'Year to date',
  'funnel.range.all':            'All time',

  'funnel.refresh':              'Refresh',
  'funnel.empty':                'No data yet for this window.',
  'funnel.loading':              'Loading...',

  'funnel.kpi.investors':        'Investors in window',
  'funnel.kpi.active':           'Active',
  'funnel.kpi.bottleneck':       'Slowest step',
  'funnel.kpi.dropoff':          'Biggest dropoff',
  'funnel.kpi.none':             'None',

  'funnel.section.stages':       'Stages · Count + conversion',
  'funnel.section.conversion':   'Conversion matrix',
  'funnel.section.bottlenecks':  'Bottlenecks',
  'funnel.section.durations':    'Step durations',
  'funnel.section.manager':      'Manager attribution',
  'funnel.section.funding':      'Funding attribution',
  'funnel.section.executive':    'Executive summary',

  'funnel.col.stage':            'Stage',
  'funnel.col.count':            'Count',
  'funnel.col.conv_prev':        'Conv. from previous',
  'funnel.col.conv_start':       'Conv. from start',
  'funnel.col.median_prev':      'Median from previous',
  'funnel.col.median_start':     'Median from start',
  'funnel.col.flags':            'Flags',

  'funnel.col.manager':          'Manager',
  'funnel.col.leads':            'Leads',
  'funnel.col.kyc':              'KYC',
  'funnel.col.signed':           'Signed',
  'funnel.col.funded':           'Funded',
  'funnel.col.certs':            'Certificates',
  'funnel.col.active':           'Active',
  'funnel.col.lead_to_funded':   'Lead → Funded',
  'funnel.col.volume':           'SEPA volume, €',
  'funnel.col.transfers':        'Transfers',
  'funnel.col.cert_value':       'Certificates, $',

  'funnel.flag.bottleneck':      'Bottleneck',
  'funnel.flag.dropoff':         'Dropoff',
  'funnel.flag.none':            '—',

  'funnel.unassigned':           '— Unassigned',
  'funnel.no_data':              'No data',

  'funnel.executive.text': (active, total, bottleneck, dropoff) =>
    `${active} active out of ${total} investors. Slowest step: ${bottleneck || 'none'}. Biggest dropoff: ${dropoff || 'none'}.`,

  'nav.funnel':                  'Investor funnel',
};
