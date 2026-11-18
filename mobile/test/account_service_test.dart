import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smishguard/account_service.dart';

const _token = 'test-session-token-0123456789abcdefghijklmnop';

http.Response _json(Object body, int status) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json'},
    );

/// Signs in through a mock server so the service holds a session.
Future<AccountService> signedInService(
  Future<http.Response> Function(http.Request request) onDelete,
) async {
  final client = MockClient((request) async {
    if (request.url.path == '/auth/login') {
      return _json({
        'access_token': _token,
        'token_type': 'bearer',
        'expires_at': '2026-11-18T20:00:00Z',
        'user': {
          'id': '7f0c4c8e-2b8a-4a3e-9a51-1d2f3e4a5b6c',
          'username': 'capstonetest',
          'created_at': '2026-11-18T08:00:00Z',
        },
      }, 200);
    }

    if (request.url.path == '/auth/delete-account') {
      return onDelete(request);
    }

    return _json({'detail': 'Not found'}, 404);
  });

  final service = AccountService(client: client);
  await service.login('capstonetest', 'a-long-test-password');
  expect(service.isSignedIn, isTrue);
  return service;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('deleteAccount sends the password, confirmation and session',
      () async {
    http.Request? sent;

    final service = await signedInService((request) async {
      sent = request;
      return http.Response('', 204);
    });

    await service.deleteAccount('a-long-test-password');

    expect(sent, isNotNull);
    expect(sent!.method, 'POST');
    expect(sent!.headers['Authorization'], 'Bearer $_token');
    expect(jsonDecode(sent!.body), {
      'password': 'a-long-test-password',
      'confirm': true,
    });

    expect(service.isSignedIn, isFalse);
    expect(service.token, isNull);
  });

  test('wrong password keeps the user signed in', () async {
    final service = await signedInService(
      (request) async => _json({'detail': 'Incorrect password.'}, 403),
    );

    await expectLater(
      service.deleteAccount('wrong-password'),
      throwsA(
        isA<AccountException>().having(
          (error) => error.message,
          'message',
          'Incorrect password. Your account was not deleted.',
        ),
      ),
    );

    expect(service.isSignedIn, isTrue);
  });

  test('expired session signs the user out', () async {
    final service = await signedInService(
      (request) async => _json({'detail': 'Sign in.'}, 401),
    );

    await expectLater(
      service.deleteAccount('a-long-test-password'),
      throwsA(isA<AccountException>()),
    );

    expect(service.isSignedIn, isFalse);
  });
}
