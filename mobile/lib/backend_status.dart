import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class BackendStatus extends StatefulWidget {
  const BackendStatus({super.key});

  @override
  State<BackendStatus> createState() => _BackendStatusState();
}

class _BackendStatusState extends State<BackendStatus> {
  bool _checking = false;
  String _status = 'Server connection has not been checked.';

  Future<void> _checkConnection() async {
    setState(() {
      _checking = true;
      _status = 'Checking connection...';
    });

    String result;

    try {
      final response = await http
          .get(Uri.parse('http://10.0.2.2:8000/health'))
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
      result = 'Cannot reach the server. Check that it is running.';
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
          onPressed: _checking ? null : _checkConnection,
          icon: const Icon(Icons.cloud_outlined),
          label: Text(
            _checking ? 'Checking...' : 'Check server connection',
          ),
        ),
        const SizedBox(height: 8),
        Text(_status, textAlign: TextAlign.center),
        const SizedBox(height: 24),
      ],
    );
  }
}