/// Rule-based warning signs for common smishing patterns.
///
/// These are simple keyword and pattern checks that run on the phone. They
/// are NOT the machine-learning model's reasoning: they point out features
/// the user can verify themselves. Genuine messages can contain them, and a
/// smishing message can have none of them.
library;

class WarningSign {
  const WarningSign({
    required this.id,
    required this.title,
    required this.detail,
  });

  /// Stable identifier, used by tests.
  final String id;
  final String title;
  final String detail;
}

const _linkTlds = 'app|asia|biz|buzz|cc|cf|click|club|cn|co|com|cyou|ga|gd|'
    'gov|gq|icu|info|io|is|lat|link|live|love|ly|makeup|me|ml|mobi|net|'
    'online|org|ph|pw|ru|shop|site|store|su|tk|to|top|vip|win|ws|xyz';

final _link = RegExp(
  r'https?://|(?<![@\w.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+'
  '(?:$_linkTlds)'
  r'(?![\w-])',
);

final _shortLink = RegExp(
  r'(?<![\w.-])(?:bit\.ly|tinyurl\.com|is\.gd|cutt\.ly|rb\.gy|t\.ly|'
  r'shorturl\.at|s\.id|tiny\.cc|ow\.ly|goo\.gl)\b',
);

final _credentials = RegExp(
  r'\b(?:otp|one[- ]time (?:pin|password|code)|password|passcode|m?pin|cvv|'
  r'card number|account number|log ?in|verify your|confirm your|kyc|'
  r'update your (?:account|details|information|e-?wallet))\b',
);

final _payment = RegExp(
  r'₱|\bphp ?\d|\bpay\b|\bpayment\b|\bfee\b|\bdeposit\w*|\btransfer\b|'
  r'\brefund\b|\bloan\b',
);

final _personalDetails = RegExp(
  r'\b(?:name|age|add|address|birthday|birth ?date|work)\s*:|'
  r'send (?:us )?your (?:complete |full )?(?:name|details|information)',
);

final _prize = RegExp(
  r'\b(?:congratulations|congrats|won|winner|prize|reward|rewards|points|'
  r'gift|claim|bonus|jackpot|panalo|nanalo|premyo)\b',
);

final _urgency = RegExp(
  r'\b(?:urgent|immediately|today|expires?|expired|expiring|within 24|'
  r'suspend(?:ed)?|disabled|locked|deactivat\w*|blocked|final notice|'
  r'last chance|limited offer|ngayon|agad)\b',
);

/// Brand names commonly impersonated in Philippine smishing.
const _brands = <String, String>{
  r'g-?cash': 'GCash',
  r'(?:pay)?maya': 'Maya',
  r'bdo': 'BDO',
  r'bpi': 'BPI',
  r'metrobank': 'Metrobank',
  r'unionbank': 'UnionBank',
  r'landbank': 'Landbank',
  r'eastwest': 'EastWest',
  r'security bank': 'Security Bank',
  r'rcbc': 'RCBC',
  r'pnb': 'PNB',
  r'china ?bank': 'China Bank',
  r'globe': 'Globe',
  r'smart': 'Smart',
  r'lbc': 'LBC',
  r'j&t|jnt': 'J&T',
  r'ninja ?van': 'Ninja Van',
  r'phl ?post(?:al)?|phil ?post': 'PHLPost',
  r'shopee': 'Shopee',
  r'lazada': 'Lazada',
  r'sss': 'SSS',
  r'philhealth': 'PhilHealth',
  r'pag-?ibig': 'Pag-IBIG',
  r'meralco': 'Meralco',
  r'facebook': 'Facebook',
};

List<String> _brandsIn(String lower) {
  final found = <String>[];

  for (final entry in _brands.entries) {
    if (RegExp(r'\b(?:' + entry.key + r')\b').hasMatch(lower) &&
        !found.contains(entry.value)) {
      found.add(entry.value);
    }
  }

  return found;
}

/// Returns the warning signs found in [text], most important first.
List<WarningSign> findWarningSigns(String text) {
  final lower = text.toLowerCase();
  final signs = <WarningSign>[];

  if (_link.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'link',
      title: 'Contains a link',
      detail: 'Do not open links in unexpected messages. Go to the official '
          'app or type the website address yourself.',
    ));
  }

  if (_shortLink.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'short_link',
      title: 'Uses a shortened link',
      detail: 'Short links such as bit.ly hide where they really go.',
    ));
  }

  if (_credentials.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'credentials',
      title: 'Mentions OTP, password or account verification',
      detail: 'Banks and e-wallets never ask for your OTP, PIN or password '
          'by text message.',
    ));
  }

  if (_payment.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'payment',
      title: 'Mentions money, a fee or a payment',
      detail: 'Be careful with requests to pay, deposit or transfer money, '
          'even small amounts.',
    ));
  }

  if (_personalDetails.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'personal_details',
      title: 'Asks for personal details',
      detail: 'Do not send your name, address, age or work details to '
          'unknown senders.',
    ));
  }

  if (_prize.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'prize',
      title: 'Offers a prize, reward or points',
      detail: 'Unexpected winnings and expiring points are common lures.',
    ));
  }

  if (_urgency.hasMatch(lower)) {
    signs.add(const WarningSign(
      id: 'urgency',
      title: 'Creates urgency',
      detail: 'Words like "today", "expires" or "suspended" pressure you to '
          'act before checking.',
    ));
  }

  final brands = _brandsIn(lower);
  if (brands.isNotEmpty) {
    signs.add(WarningSign(
      id: 'brand',
      title: 'Mentions ${brands.join(', ')}',
      detail: 'Scammers often pretend to be banks, e-wallets, telcos, '
          'couriers or agencies. Check through their official app or '
          'hotline, not this message.',
    ));
  }

  return signs;
}
