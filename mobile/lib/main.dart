import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'backend_status.dart';
import 'screenshot_input.dart';

void main() {
  runApp(const SmishGuardApp());
}

class SmishGuardApp extends StatelessWidget {
  const SmishGuardApp({super.key, this.client});

  final http.Client? client;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SMISHGUARD',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        useMaterial3: true,
      ),
      home: MessageScreen(client: client),
    );
  }
}

class MessageScreen extends StatefulWidget {
  const MessageScreen({super.key, this.client});

  final http.Client? client;

  @override
  State<MessageScreen> createState() => _MessageScreenState();
}

class _MessageScreenState extends State<MessageScreen> {
  final _messageController = TextEditingController();
  late final http.Client _client;

  String? _error;
  String? _result;
  bool _loading = false;
  bool _ocrLoading = false;

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? http.Client();
  }

  @override
  void dispose() {
    _messageController.dispose();

    if (widget.client == null) {
      _client.close();
    }

    super.dispose();
  }

  Future<void> _analyze() async {
    if (_loading || _ocrLoading) return;

    final text = _messageController.text.trim();

    if (text.isEmpty) {
      setState(() {
        _error = 'Enter a message first.';
        _result = null;
      });
      return;
    }

    setState(() {
      _error = null;
      _result = null;
      _loading = true;
    });

    String result;

    try {
      final response = await _client
          .post(
            Uri.parse('http://10.0.2.2:8000/analyze'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'text': text}),
          )
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 503) {
        final data = jsonDecode(response.body);
        final detail =
            data is Map<String, dynamic> ? data['detail'] : null;

        if (detail is Map<String, dynamic> &&
            detail['code'] == 'MODEL_NOT_READY') {
          result =
              'The server received your message. '
              'Detection is not available yet. '
              'No risk assessment was made.';
        } else {
          result = 'Analysis is temporarily unavailable. Try again later.';
        }
      } else if (response.statusCode == 422) {
        result =
            'The server rejected the submission. '
            'Enter one message containing 1–5,000 characters.';
      } else {
        result =
            'The server returned an unexpected response. '
            'No assessment is available.';
      }
    } on TimeoutException {
      result = 'The request timed out. No assessment was received.';
    } on http.ClientException {
      result = 'Cannot reach the server. Check your connection and retry.';
    } catch (_) {
      result =
          'The response could not be processed. '
          'No assessment is available.';
    }

    if (!mounted) return;

    setState(() {
      _loading = false;
      _result = result;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SMISHGUARD'),
        centerTitle: true,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const BackendStatus(),
            const Icon(
              Icons.shield_outlined,
              size: 64,
              color: Colors.teal,
            ),
            const SizedBox(height: 20),
            Text(
              'Check a suspicious message',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 12),
            const Text(
              'Type or paste an English SMS below. '
              'Remove passwords, OTPs, and account details first.',
            ),
            const SizedBox(height: 24),
            ScreenshotInput(
  enabled: !_loading,
  onBusyChanged: (busy) {
    setState(() {
      _ocrLoading = busy;
    });
  },
  onTextExtracted: (text) {
    setState(() {
      _messageController.text = text;
      _error = null;
      _result = null;
    });
  },
),
            TextField(
              controller: _messageController,
              readOnly: _loading || _ocrLoading,
              minLines: 6,
              maxLines: 12,
              maxLength: 5000,
              onChanged: (_) {
                setState(() {
                  _error = null;
                  _result = null;
                });
              },
              decoration: InputDecoration(
                labelText: 'SMS message',
                hintText: 'Paste the message here...',
                alignLabelWithHint: true,
                border: const OutlineInputBorder(),
                errorText: _error,
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: (_loading || _ocrLoading) ? null : _analyze,
              icon: _loading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.search),
              label: Text(_loading ? 'Submitting...' : 'Analyze Message'),
            ),
            if (_result != null) ...[
              const SizedBox(height: 20),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(_result!),
                  ),
                ),
              ),
            ],
            const SizedBox(height: 16),
            const Text(
              'Messages are sent to the analysis server. '
              'Detection is not available yet.',
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}