import 'package:flutter/material.dart';

void main() {
  runApp(const SmishGuardApp());
}

class SmishGuardApp extends StatelessWidget {
  const SmishGuardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SMISHGUARD',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        useMaterial3: true,
      ),
      home: const MessageScreen(),
    );
  }
}

class MessageScreen extends StatefulWidget {
  const MessageScreen({super.key});

  @override
  State<MessageScreen> createState() => _MessageScreenState();
}

class _MessageScreenState extends State<MessageScreen> {
  final _messageController = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  void _analyze() {
    if (_messageController.text.trim().isEmpty) {
      setState(() {
        _error = 'Enter a message first.';
      });
      return;
    }

    setState(() {
      _error = null;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Analysis is not available yet. No message has been sent.',
        ),
      ),
    );
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
            TextField(
              controller: _messageController,
              minLines: 6,
              maxLines: 12,
              maxLength: 5000,
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
              onPressed: _analyze,
              icon: const Icon(Icons.search),
              label: const Text('Analyze Message'),
            ),
            const SizedBox(height: 16),
            const Text(
              'Prototype: message detection is not connected yet.',
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}