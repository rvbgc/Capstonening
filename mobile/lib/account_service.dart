import 'dart:async';
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class AccountException implements Exception {
  const AccountException(this.message);

  final String message;

  @override
  String toString() => message;
}

class AccountService {
  AccountService({required this.client});

  static const baseUrl = 'http://10.0.2.2:8000';
  static const _tokenKey = 'smishguard_user_session';

  final http.Client client;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  String? _token;
  Map<String, dynamic>? _user;

  String? get token => _token;
  String? get userId => _user?['id'] as String?;
  String get username => _user?['username'] as String? ?? '';
  bool get isSignedIn => _token != null && _user != null;

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = false,
    String? tokenOverride,
  }) async {
    final usedToken = tokenOverride ?? _token;

    if (authenticated && usedToken == null) {
      throw const AccountException('Sign in first.');
    }

    final headers = <String, String>{
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json',
      if (authenticated) 'Authorization': 'Bearer $usedToken',
    };

    final uri = Uri.parse('$baseUrl$path');
    final encodedBody = body == null ? null : jsonEncode(body);

    late final http.Response response;

    try {
      final Future<http.Response> pending;

      switch (method) {
        case 'GET':
          pending = client.get(uri, headers: headers);
          break;
        case 'POST':
          pending = client.post(
            uri,
            headers: headers,
            body: encodedBody,
          );
          break;
        case 'DELETE':
          pending = client.delete(uri, headers: headers);
          break;
        default:
          throw const AccountException('Unsupported request.');
      }

      response = await pending.timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw const AccountException(
        'The request timed out. Check the current status before retrying.',
      );
    } on http.ClientException {
      throw const AccountException(
        'Cannot reach the server. Check your connection.',
      );
    }

    if (response.statusCode == 401) {
      if (authenticated) {
        if (_token == usedToken) {
          await forgetSession();
        }
        throw const AccountException(
          'Your session has expired. Sign in again.',
        );
      }

      throw const AccountException('Incorrect username or password.');
    }

    if (response.statusCode >= 400) {
      final message = switch (response.statusCode) {
        409 => 'That username is already registered.',
        422 => 'Check your username and password requirements.',
        429 => 'Too many attempts. Wait a minute and try again.',
        404 => 'This history entry is no longer available.',
        503 => 'The service is temporarily unavailable.',
        _ => 'The request could not be completed.',
      };
      throw AccountException(message);
    }

    if (response.statusCode == 204) {
      return <String, dynamic>{};
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! Map<String, dynamic>) {
      throw const AccountException('The server returned an invalid response.');
    }

    return decoded;
  }

  Future<void> restore() async {
    if (isSignedIn) return;

    final savedToken = await _storage.read(key: _tokenKey);
    if (savedToken == null || savedToken.isEmpty) return;

    _token = savedToken;

    final profile = await _request(
      'GET',
      '/auth/me',
      authenticated: true,
    );

    if (profile['id'] is! String || profile['username'] is! String) {
      await forgetSession();
      throw const AccountException('The account response was invalid.');
    }

    _user = profile;
  }

  Future<void> register(String username, String password) async {
    await _request(
      'POST',
      '/auth/register',
      body: {'username': username, 'password': password},
    );
  }

  Future<void> login(String username, String password) async {
    final data = await _request(
      'POST',
      '/auth/login',
      body: {'username': username, 'password': password},
    );

    final newToken = data['access_token'];
    final profile = data['user'];

    if (newToken is! String ||
        newToken.isEmpty ||
        profile is! Map<String, dynamic> ||
        profile['id'] is! String ||
        profile['username'] is! String) {
      throw const AccountException('The sign-in response was invalid.');
    }

    try {
      await _storage.write(key: _tokenKey, value: newToken);
    } catch (_) {
      try {
        await _request(
          'POST',
          '/auth/logout',
          authenticated: true,
          tokenOverride: newToken,
        );
      } catch (_) {
        // The newly issued session will otherwise expire on the server.
      }

      throw const AccountException(
        'Secure storage could not save your session. Sign-in was not completed.',
      );
    }

    _token = newToken;
    _user = profile;
  }

  Future<bool> forgetSession() async {
    _token = null;
    _user = null;

    try {
      await _storage.delete(key: _tokenKey);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<String> logout() async {
    var serverConfirmed = true;

    try {
      if (_token != null) {
        await _request('POST', '/auth/logout', authenticated: true);
      }
    } catch (_) {
      serverConfirmed = false;
    }

    final localCleared = await forgetSession();

    if (!localCleared) {
      return 'The saved session could not be removed from this device. '
          'Tap Sign out again to retry.';
    }

    return serverConfirmed
        ? 'Signed out.'
        : 'Signed out on this device. Server logout could not be confirmed.';
  }

  Future<Map<String, dynamic>> listHistory({int offset = 0}) {
    return _request(
      'GET',
      '/history?limit=20&offset=$offset',
      authenticated: true,
    );
  }

  Future<Map<String, dynamic>> openHistory(String id) {
    return _request(
      'GET',
      '/history/${Uri.encodeComponent(id)}',
      authenticated: true,
    );
  }

  Future<void> deleteHistory(String id) async {
    await _request(
      'DELETE',
      '/history/${Uri.encodeComponent(id)}',
      authenticated: true,
    );
  }

  Future<void> clearHistory() async {
    await _request(
      'DELETE',
      '/history?confirm=true',
      authenticated: true,
    );
  }
}