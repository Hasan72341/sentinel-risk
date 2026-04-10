r"""Sentiment Analysis Engine: rule-based news and commentary sentiment.

Provides lexicon-based sentiment scoring with keyword matching, negation
handling and entity-level aggregation. Works offline; no external API calls.

English text only. The lexicons cover wording common in English-language
filings, exchange announcements and financial press in India, China, Japan
and South Korea (for example "turnover", "profit after tax", "ordinary
income", "upward revision", "limit up", "rating downgrade").

Simplified, for analysis and learning; a keyword model is not a substitute
for reading the source text.
"""

import re
from collections import Counter


# -- English sentiment lexicons ---------------------------------------------

POSITIVE_EN = frozenset([
    # Growth / profit
    'growth', 'grow', 'increase', 'rise', 'rose', 'risen', 'gain', 'profit',
    'profitable', 'surge', 'jump', 'climb', 'soar', 'expand', 'expansion',
    'improve', 'improvement', 'recovery', 'recover', 'rebound', 'turnaround',
    'accelerate', 'momentum', 'boom', 'rally', 'record', 'high', 'higher',
    'bullish', 'positive', 'upside', 'surplus',
    # Results versus expectations
    'outperform', 'beat', 'exceed', 'upgrade', 'upward', 'raise', 'raised',
    'strong', 'stronger', 'robust', 'solid', 'healthy', 'resilient', 'stable',
    'steady', 'efficient', 'optimal', 'breakthrough', 'opportunity',
    # Shareholder returns and corporate actions
    'dividend', 'bonus', 'buyback', 'innovation', 'acquire', 'merger',
    'approval', 'approved', 'win', 'won', 'award', 'awarded',
    # Credit and counterparty wording
    'deleveraging', 'repaid', 'prepaid', 'oversubscribed', 'affirmed',
    'confidence', 'trust', 'transparent', 'comfortable',
    # Recommendations
    'buy', 'long', 'overweight', 'initiate', 'accumulate',
])

NEGATIVE_EN = frozenset([
    # Decline / loss
    'decline', 'decrease', 'fall', 'fell', 'fallen', 'drop', 'loss', 'lose',
    'lost', 'crash', 'slump', 'plunge', 'tumble', 'slide', 'sink', 'shrink',
    'contraction', 'slowdown', 'weak', 'weaker', 'weakness', 'poor', 'low',
    'lower', 'bearish', 'negative', 'downside', 'deficit', 'shortfall',
    # Results versus expectations
    'underperform', 'miss', 'missed', 'downgrade', 'downward', 'cut', 'worse',
    'deteriorate', 'deterioration', 'erosion', 'pressure', 'squeeze',
    # Credit and counterparty wording
    'default', 'defaulted', 'delinquent', 'delinquency', 'overdue', 'arrears',
    'impairment', 'impaired', 'writedown', 'writeoff', 'provision', 'npa',
    'slippage', 'restructuring', 'moratorium', 'insolvency', 'insolvent',
    'bankrupt', 'bankruptcy', 'liquidation', 'breach', 'breached', 'waiver',
    'debt', 'overleveraged', 'pledged', 'haircut',
    # Market stress
    'risk', 'crisis', 'recession', 'bust', 'correction', 'volatile',
    'volatility', 'uncertainty', 'selloff', 'outflow', 'devaluation',
    'depreciation', 'halt', 'halted', 'suspended', 'suspension', 'delisting',
    # Governance and legal
    'fraud', 'misstatement', 'restatement', 'qualified', 'resignation',
    'probe', 'investigation', 'lawsuit', 'litigation', 'penalty', 'fine',
    'sanction', 'conflict', 'tension', 'layoff', 'strike', 'recall',
    # Recommendations
    'sell', 'short', 'underweight', 'reduce', 'avoid',
])

# Multi-word phrases scored before single tokens. Each phrase counts once and
# its words are not scored again individually.
POSITIVE_PHRASES_EN = (
    'profit after tax rose', 'profit after tax increased', 'net sales rose',
    'net sales increased', 'turnover rose', 'turnover increased',
    'ordinary income rose', 'ordinary income increased', 'upward revision',
    'rating upgrade', 'outlook revised to positive', 'outlook positive',
    'limit up', 'upper circuit', 'order book', 'order inflow', 'market share gain',
    'debt reduction', 'interest coverage improved', 'capital adequacy improved',
    'record high', 'above consensus', 'ahead of guidance',
)

NEGATIVE_PHRASES_EN = (
    'profit after tax fell', 'profit after tax declined', 'net sales fell',
    'net sales declined', 'turnover fell', 'turnover declined',
    'ordinary income fell', 'ordinary income declined', 'ordinary loss',
    'downward revision', 'rating downgrade', 'outlook revised to negative',
    'outlook negative', 'credit watch', 'limit down', 'lower circuit',
    'margin call', 'covenant breach', 'limit breach', 'going concern',
    'non performing', 'bad loans', 'capital flight', 'profit warning',
    'trading halt', 'below consensus', 'record low', 'audit qualification',
)

INTENSIFIERS_EN = frozenset([
    'very', 'extremely', 'highly', 'absolutely', 'significantly', 'sharply',
    'remarkably', 'exceptionally', 'particularly', 'especially', 'incredibly',
    'substantially', 'materially', 'steeply',
])
NEGATORS_EN = frozenset([
    'not', 'no', 'never', 'neither', 'nor', 'hardly', 'barely', 'scarcely',
    'without', 'lack', 'absence', 'despite', 'excluding',
])

_SUFFIXES = ('ing', 'ed', 'es', 's', 'd')


def _tokenize_en(text: str) -> list[str]:
    """Simple English tokenizer (lower-cased alphabetic words)."""
    return re.findall(r'[a-z]+', text.lower())


def _lexicon_form(token: str, lexicon: frozenset) -> str | None:
    """Return the lexicon entry matching ``token``, allowing simple inflections.

    "increased" matches "increase", "gains" matches "gain", "rising" matches
    "rise". Returns None when no form of the token is in the lexicon.
    """
    if token in lexicon:
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            stem = token[: -len(suffix)]
            if stem in lexicon:
                return stem
            if stem + 'e' in lexicon:
                return stem + 'e'
    return None


def _match_phrases(tokens: list[str], phrases: tuple[str, ...]) -> tuple[list[str], set[int]]:
    """Find whole-word phrase matches; return matched phrases and token indexes used."""
    found: list[str] = []
    used: set[int] = set()
    for phrase in phrases:
        words = phrase.split()
        size = len(words)
        for start in range(len(tokens) - size + 1):
            if tokens[start:start + size] == words:
                found.append(phrase)
                used.update(range(start, start + size))
    return found, used


def _score_text(text: str) -> dict:
    """Score a single English text's sentiment."""
    tokens = _tokenize_en(text)
    intensifiers = INTENSIFIERS_EN
    negators = NEGATORS_EN

    pos_score = 0.0
    neg_score = 0.0
    pos_words = []
    neg_words = []

    pos_phrases, pos_used = _match_phrases(tokens, POSITIVE_PHRASES_EN)
    neg_phrases, neg_used = _match_phrases(tokens, NEGATIVE_PHRASES_EN)
    phrase_tokens = pos_used | neg_used
    pos_score += 1.5 * len(pos_phrases)
    neg_score += 1.5 * len(neg_phrases)
    pos_words.extend(pos_phrases)
    neg_words.extend(neg_phrases)

    for i, token in enumerate(tokens):
        if i in phrase_tokens:
            continue
        multiplier = 1.0
        negated = False

        # Check previous 2 words for intensifiers/negators
        for j in range(max(0, i - 2), i):
            if tokens[j] in intensifiers:
                multiplier *= 1.5
            if tokens[j] in negators:
                negated = True

        pos_form = _lexicon_form(token, POSITIVE_EN)
        neg_form = None if pos_form else _lexicon_form(token, NEGATIVE_EN)
        if pos_form:
            if negated:
                neg_score += 0.8 * multiplier
                neg_words.append(pos_form)
            else:
                pos_score += 1.0 * multiplier
                pos_words.append(pos_form)
        elif neg_form:
            if negated:
                pos_score += 0.5 * multiplier
                pos_words.append(neg_form)
            else:
                neg_score += 1.0 * multiplier
                neg_words.append(neg_form)

    total = pos_score + neg_score
    if total == 0:
        sentiment_score = 0.0
        sentiment_label = 'neutral'
    else:
        sentiment_score = (pos_score - neg_score) / total  # [-1, 1]
        if sentiment_score > 0.2:
            sentiment_label = 'positive'
        elif sentiment_score < -0.2:
            sentiment_label = 'negative'
        else:
            sentiment_label = 'neutral'

    return {
        'pos_score': round(pos_score, 3),
        'neg_score': round(neg_score, 3),
        'sentiment_score': round(sentiment_score, 4),
        'label': sentiment_label,
        'pos_words': pos_words[:5],
        'neg_words': neg_words[:5],
        'token_count': len(tokens),
    }


def analyze_sentiment(
    texts: list[str],
    labels: list[str] | None = None,
    weights: list[float] | None = None,
) -> dict:
    """Analyze sentiment for a batch of texts.

    Args:
        texts: List of text strings (news headlines, social posts, etc.).
        labels: Optional labels for each text (e.g., source names).
        weights: Optional importance weights per text.
    """
    if not texts:
        return {'error': 'No texts provided'}

    n = len(texts)
    if labels is None:
        labels = [f'Text {i+1}' for i in range(n)]
    if weights is None:
        weights = [1.0] * n

    results = []
    score_sum = 0.0
    weight_sum = 0.0
    label_counts = Counter()

    for i, text in enumerate(texts):
        score = _score_text(text)
        score['text_preview'] = text[:120] + ('...' if len(text) > 120 else '')
        score['label_name'] = labels[i]
        score['lang'] = 'en'
        score['weight'] = weights[i]
        results.append(score)

        score_sum += score['sentiment_score'] * weights[i]
        weight_sum += weights[i]
        label_counts[score['label']] += 1

    avg_score = score_sum / weight_sum if weight_sum > 0 else 0
    if avg_score > 0.2:
        overall_label = 'positive'
    elif avg_score < -0.2:
        overall_label = 'negative'
    else:
        overall_label = 'neutral'

    # Sentiment distribution
    pos_count = sum(1 for r in results if r['label'] == 'positive')
    neg_count = sum(1 for r in results if r['label'] == 'negative')
    neu_count = sum(1 for r in results if r['label'] == 'neutral')

    # Top keywords
    all_pos = []
    all_neg = []
    for r in results:
        all_pos.extend(r['pos_words'])
        all_neg.extend(r['neg_words'])
    top_positive = [w for w, _ in Counter(all_pos).most_common(10)]
    top_negative = [w for w, _ in Counter(all_neg).most_common(10)]

    # Time series (if labels are dates or ordered)
    score_series = [round(r['sentiment_score'], 4) for r in results]

    return {
        'overall': {
            'score': round(avg_score, 4),
            'label': overall_label,
            'positive_pct': round(pos_count / n * 100, 1),
            'negative_pct': round(neg_count / n * 100, 1),
            'neutral_pct': round(neu_count / n * 100, 1),
        },
        'distribution': {
            'positive': pos_count,
            'negative': neg_count,
            'neutral': neu_count,
        },
        'top_keywords': {
            'positive': top_positive,
            'negative': top_negative,
        },
        'score_series': score_series,
        'texts': results,
        'total_texts': n,
    }


def stock_sentiment_analysis(
    symbol: str,
    news_texts: list[str],
    social_texts: list[str] | None = None,
) -> dict:
    """Analyze sentiment for one counterparty, issuer or sector label.

    Combines news and social media sentiment with weighted aggregation.
    """
    if not news_texts:
        return {'error': 'No news texts provided'}

    # Analyze news (weight 2x)
    news_labels = [f'{symbol} - News {i+1}' for i in range(len(news_texts))]
    news_weights = [2.0] * len(news_texts)
    news_result = analyze_sentiment(news_texts, news_labels, news_weights)

    # Analyze social (weight 1x)
    social_result = None
    if social_texts and len(social_texts) > 0:
        social_labels = [f'{symbol} - Social {i+1}' for i in range(len(social_texts))]
        social_weights = [1.0] * len(social_texts)
        social_result = analyze_sentiment(social_texts, social_labels, social_weights)

    # Combined score
    if social_result:
        total_news_weight = sum(news_weights)
        total_social_weight = len(social_texts)
        combined_score = (
            news_result['overall']['score'] * total_news_weight +
            social_result['overall']['score'] * total_social_weight
        ) / (total_news_weight + total_social_weight)
    else:
        combined_score = news_result['overall']['score']

    if combined_score > 0.2:
        signal = 'bullish'
    elif combined_score < -0.2:
        signal = 'bearish'
    else:
        signal = 'neutral'

    return {
        'symbol': symbol,
        'combined_score': round(combined_score, 4),
        'signal': signal,
        'news_sentiment': {
            'score': news_result['overall']['score'],
            'label': news_result['overall']['label'],
            'article_count': len(news_texts),
        },
        'social_sentiment': {
            'score': social_result['overall']['score'] if social_result else None,
            'label': social_result['overall']['label'] if social_result else None,
            'post_count': len(social_texts) if social_texts else 0,
        },
        'keyword_summary': {
            'positive': news_result['top_keywords']['positive'][:5],
            'negative': news_result['top_keywords']['negative'][:5],
        },
        'recommendation': _generate_recommendation(combined_score, signal),
    }


def _generate_recommendation(score: float, signal: str) -> str:
    """Generate a brief recommendation based on sentiment."""
    if signal == 'bullish':
        if score > 0.5:
            return 'Strong positive sentiment detected. Consider increasing position or initiating coverage. Monitor for sentiment reversal.'
        else:
            return 'Moderately positive sentiment. Current sentiment supports holding or cautiously adding to position.'
    elif signal == 'bearish':
        if score < -0.5:
            return 'Strong negative sentiment detected. Consider reducing exposure or setting tighter stop-losses. Wait for sentiment stabilization.'
        else:
            return 'Moderately negative sentiment. Exercise caution. May present buying opportunity if fundamentals remain strong.'
    else:
        return 'Neutral sentiment. No strong directional signal from sentiment analysis. Rely on fundamental and technical analysis for decisions.'


def sentiment_demo() -> dict:
    """Demo sentiment analysis on illustrative headlines.

    The issuers and headlines below are fictional sample data written for this
    demo. They are not real companies, news or market data.
    """
    news = [
        'Meridian Steel Works (India) profit after tax rose 40 percent to a record high on strong domestic demand',
        'Lotus Harbor Petrochemical (China) reports net sales increased 25 percent year on year as exports recover',
        'Central bank keeps policy rate unchanged; bond market reaction positive and stable',
        'Falling crude prices put pressure on refinery shares; analysts cut estimates',
        'Monthly review: broad equity index closed 3 percent higher on steady foreign inflows',
        'Kiso Motor Components (Japan) announces upward revision to ordinary income forecast on strong orders',
        'New export restrictions may hurt Hanbit Pharma (South Korea); shares fell sharply',
        'Sakura Grid Systems chief executive: turnover rose 50 percent and margins continue to improve',
        'Rating downgrade for Eastgate Commercial Bank after bad loans increased and provisions were raised',
        'Namsan Digital Bank expands its payments platform; innovation drives customer growth',
        'Currency volatility triggers margin call pressure for importers; uncertainty remains high',
        'Analysts see positive outlook for technology hardware exporters next year',
    ]

    social = [
        'Meridian Steel had a very strong day, added to my position',
        'Lotus Harbor dropped again, getting worried about the debt',
        'Avoid Eastgate Commercial Bank, I lost money on it',
        'Index is positive, the market looks like it is recovering',
        'Kiso Motor is doing well, solid profit this quarter',
        'The export restrictions hurt everything, weak sentiment all round',
    ]

    # Per-sector analysis (sector label -> illustrative headlines)
    stock_news = {
        'Steel': [
            'Meridian Steel Works profit after tax rose 40 percent',
            'Steel exports increased 30 percent on strong regional demand',
            'Global steel prices fell 5 percent during the month',
        ],
        'Petrochemical': [
            'Lotus Harbor Petrochemical net sales increased 25 percent',
            'Falling crude prices put pressure on petrochemical margins',
        ],
        'Banking': [
            'Policy rate left unchanged',
            'Rating downgrade for Eastgate Commercial Bank after bad loans increased',
            'Namsan Digital Bank innovation drives customer growth',
        ],
        'Automotive': [
            'Kiso Motor Components sees strong order growth',
            'Upward revision announced for auto component makers',
        ],
        'Technology': [
            'Sakura Grid Systems turnover rose 50 percent',
            'Positive outlook for technology hardware exporters',
        ],
    }

    stock_results = []
    for sym, texts in stock_news.items():
        r = stock_sentiment_analysis(sym, texts)
        stock_results.append({
            'symbol': sym,
            'score': r['combined_score'],
            'signal': r['signal'],
            'news_count': r['news_sentiment']['article_count'],
            'recommendation': r['recommendation'],
        })

    # Overall market sentiment
    overall = analyze_sentiment(news, ['News ' + str(i+1) for i in range(len(news))])

    return {
        'demo_info': {
            'description': (
                'Illustrative sample data: 12 fictional headlines and 6 fictional posts '
                'covering India, China, Japan and South Korea. Not real news or market data.'
            ),
            'news_count': len(news),
            'social_count': len(social),
            'stocks_analyzed': list(stock_news.keys()),
            'is_sample_data': True,
        },
        'market_overall': overall['overall'],
        'market_distribution': overall['distribution'],
        'market_keywords': overall['top_keywords'],
        'score_timeline': overall['score_series'],
        'per_stock': stock_results,
    }
