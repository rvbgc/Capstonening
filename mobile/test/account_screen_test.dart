import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smishguard/account_screen.dart';
import 'package:smishguard/account_service.dart';

http.Response _json(Object body, int status) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json'},
    );

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets('Delete my account asks for the password and signs out',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    Map<String, dynamic>? deleteBody;

    final client = MockClient((request) async {
      switch (request.url.path) {
        case '/auth/login':
          return _json({
            'access_token': 'test-session-token-0123456789abcdefghijklmnop',
            'token_type': 'bearer',
            'expires_at': '2026-11-18T20:00:00Z',
            'user': {
              'id': '7f0c4c8e-2b8a-4a3e-9a51-1d2f3e4a5b6c',
              'username': 'capstonetest',
              'created_at': '2026-11-18T08:00:00Z',
            },
          }, 200);
        case '/history':
          return _json({'items': [], 'has_more': false}, 200);
        case '/auth/delete-account':
          deleteBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response('', 204);
      }
      return _json({'detail': 'Not found'}, 404);
    });
    addTearDown(client.close);

    final account = AccountService(client: client);
    await account.login('capstonetest', 'a-long-test-password');

    await tester.pumpWidget(
      MaterialApp(home: AccountScreen(account: account)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Signed in as capstonetest'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('delete-account-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('delete-account-dialog')), findsOneWidget);

    // The delete button stays disabled until a password is entered.
    final confirm = find.byKey(const ValueKey('confirm-delete-account-button'));
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(
      find.byKey(const ValueKey('delete-account-password')),
      'a-long-test-password',
    );
    await tester.pump();
    await tester.tap(confirm);
    await tester.pumpAndSettle();

    expect(deleteBody, {
      'password': 'a-long-test-password',
      'confirm': true,
    });
    expect(account.isSignedIn, isFalse);
    expect(
      find.text('Your account and all saved analyses were deleted.'),
      findsOneWidget,
    );
    expect(find.text('Sign in'), findsWidgets);
  });

  testWidgets('Cancelling the dialog does not delete the account',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    var deleteCalls = 0;

    final client = MockClient((request) async {
      switch (request.url.path) {
        case '/auth/login':
          return _json({
            'access_token': 'test-session-token-0123456789abcdefghijklmnop',
            'token_type': 'bearer',
            'expires_at': '2026-11-18T20:00:00Z',
            'user': {
              'id': '7f0c4c8e-2b8a-4a3e-9a51-1d2f3e4a5b6c',
              'username': 'capstonetest',
              'created_at': '2026-11-18T08:00:00Z',
            },
          }, 200);
        case '/history':
          return _json({'items': [], 'has_more': false}, 200);
        case '/auth/delete-account':
          deleteCalls++;
          return http.Response('', 204);
      }
      return _json({'detail': 'Not found'}, 404);
    });
    addTearDown(client.close);

    final account = AccountService(client: client);
    await account.login('capstonetest', 'a-long-test-password');

    await tester.pumpWidget(
      MaterialApp(home: AccountScreen(account: account)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('delete-account-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(deleteCalls, 0);
    expect(account.isSignedIn, isTrue);
    expect(find.text('Signed in as capstonetest'), findsOneWidget);
  });
}
