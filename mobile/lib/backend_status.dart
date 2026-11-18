import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'api_config.dart';

class BackendStatus extends StatefulWidget {
  const BackendStatus({super.key, this.client});

  /// Optional HTTP client, injected by tests. A temporary client is used
  /// when none is given.
  final http.Client? client;

  @override
  State<BackendStatus> createState() => _BackendStatusState();
}

class _BackendStatusState extends State<BackendStatus> {
  bool _checking = false;
  String _status = 'Server connection has not been checked.';

  @override
  void initState() {
    super.initState();

    // Check once automatically when the screen opens.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _checkConnection();
    });
  }

  Future<void> _checkConnection() async {
    if (_checking) return;

    setState(() {
      _checking = true;
      _status = 'Checking connection...';
    });

    final ownsClient = widget.client == null;
    final client = widget.client ?? http.Client();

    String result;

    try {
      final response = await client
          .get(Uri.parse('$apiBaseUrl/health'))
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);

        if (data is Map<String, dynamic> && data['status'] == 'ok') {
          result = data['model_ready'] == true
              ? 'Server connected. Model is available.'
              : 'Server connected. Detection is not ready yet.';
        } else {
          result = 'The server returned an unexpected response.';
        }
      } else {
        result = 'Server check failed (${response.statusCode}).';
      }
    } catch (_) {
      result = 'Cannot reach the server at $apiBaseUrl. '
          'Check that it is running.';
    } finally {
      if (ownsClient) client.close();
    }

    if (!mounted) return;

    setState(() {
      _checking = false;
      _status = result;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        OutlinedButton.icon(
          key: const ValueKey('check-server-button'),
          onPressed: _checking ? null : _checkConnection,
          icon: const Icon(Icons.cloud_outlined),
          label: Text(
            _checking ? 'Checking...' : 'Check server connection',
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _status,
          key: const ValueKey('server-status-text'),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}
