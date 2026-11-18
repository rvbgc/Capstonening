import 'package:flutter/material.dart';

/// Explains what SMISHGUARD does, how data is handled, and its limits.
class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  static const _sections = <(IconData, String, List<String>)>[
    (
      Icons.shield_outlined,
      'What SMISHGUARD does',
      [
        'Checks an English SMS for signs of smishing (SMS phishing).',
        'Accepts typed or pasted text, or a screenshot that is converted to '
            'text for you to review.',
        'Lets you report a suspicious message for review.',
      ],
    ),
    (
      Icons.fact_check_outlined,
      'How a message is checked',
      [
        'SMS assessment: a machine-learning model trained on labelled '
            'messages predicts "smishing" or "not detected".',
        'URL check: links in the message are compared with a cached '
            'PhishHunt list of reported phishing sites.',
        'Warning signs: simple rules point out common patterns such as '
            'links, OTP requests, urgency or prizes. These rules are not '
            "the model's reasoning.",
        'The three results are shown separately so you can judge each one.',
      ],
    ),
    (
      Icons.lock_outline,
      'Your data',
      [
        'Messages are sent to the SMISHGUARD server only when you tap '
            'Analyze or Report.',
        'History is optional. Only analyses you choose to save are stored, '
            'and only your latest 100.',
        'You can delete one entry, clear all history, or delete your '
            'account in Account & history.',
        'Passwords are stored as one-way hashes. Your sign-in on this phone '
            'is kept in secure storage.',
        'Reports are not linked to your account and stay pending until '
            'reviewed. Screenshots are not stored.',
      ],
    ),
    (
      Icons.info_outline,
      'Limitations',
      [
        'This is a research prototype. Results can be wrong in both '
            'directions.',
        '"Not detected" does not mean a message is safe. A link that is '
            'not in the PhishHunt list is not proven safe.',
        'The model was trained mainly on English messages and may not '
            'handle Filipino or Taglish well.',
        'Text read from screenshots can contain mistakes. Always check it.',
        'Always verify through the official app, website or hotline of the '
            'company the message claims to be from.',
      ],
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('About SMISHGUARD')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          for (final (icon, title, points) in _sections) ...[
            Card(
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(icon, color: theme.colorScheme.primary),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            title,
                            style: theme.textTheme.titleMedium,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    for (final point in points)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('•  '),
                            Expanded(child: Text(point)),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
          Text(
            'SMISHGUARD prototype 1.0 · Capstone project',
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
