import 'package:flutter_test/flutter_test.dart';
import 'package:smishguard/warning_signs.dart';

List<String> ids(String text) =>
    findWarningSigns(text).map((sign) => sign.id).toList();

void main() {
  test('GCash account-disabled message', () {
    final found = ids(
      'Your G-Cash account has been temporarily disabled! Please update your '
      'GCash e-wallet. Confirm your Gcash here: kycconfirmgcash.online',
    );

    expect(found, containsAll(['link', 'credentials', 'urgency', 'brand']));
    expect(found, isNot(contains('short_link')));
  });

  test('Postal fee message', () {
    expect(
      ids(
        'PHL Postal: We are unable to deliver your package due to wrong '
        'address. Please update the address and pay P17.05. '
        'https://phlpostl-gove.com/ph',
      ),
      containsAll(['link', 'payment', 'brand']),
    );
  });

  test('Prize message asking for personal details', () {
    expect(
      ids(
        "Congratulations! Your no. had won! Php480k KOPIKO MAG-KAPERA. "
        'To claim, Please Send Your Complete\nNAME:\nAGE:\nADD:\nWORK:',
      ),
      containsAll(['prize', 'personal_details', 'payment']),
    );
  });

  test('Filipino deposit lure with a short link', () {
    expect(
      ids(
        'Hello po, May reward po sa bawat deposito. May refund din po sa '
        'unang loss. Check niyo po dito: bit.ly/4vaqjXh',
      ),
      containsAll(['link', 'short_link', 'prize', 'payment']),
    );
  });

  test('Brand names are listed in the title', () {
    final brand = findWarningSigns('BDO and BPI customers: update today')
        .firstWhere((sign) => sign.id == 'brand');

    expect(brand.title, 'Mentions BDO, BPI');
  });

  test('Ordinary message has no warning signs', () {
    expect(
      ids(
        'Hi! Our group meeting is moved to 3 PM tomorrow at the library. '
        'Please bring your laptop.',
      ),
      isEmpty,
    );
  });

  test('Email address alone is not counted as a link', () {
    expect(
      ids('Contact the affiliate (someone@gmail.com) for more details'),
      isNot(contains('link')),
    );
  });

  test('Filipino word "dito" is not mistaken for a brand', () {
    expect(ids('Kita tayo dito mamaya.'), isEmpty);
  });
}
