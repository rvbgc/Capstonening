import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smishguard/main.dart';

void main() {
  testWidgets('Empty message shows a validation error', (tester) async {
    await tester.pumpWidget(const SmishGuardApp());

    expect(find.text('SMISHGUARD'), findsOneWidget);

    await tester.tap(find.text('Analyze Message'));
    await tester.pump();

    expect(find.text('Enter a message first.'), findsOneWidget);
  });

  testWidgets('Entered message shows the prototype notice', (tester) async {
    await tester.pumpWidget(const SmishGuardApp());

    await tester.enterText(
      find.byType(TextField),
      'This is a sample message.',
    );
    await tester.tap(find.text('Analyze Message'));
    await tester.pump();

    expect(
      find.text(
        'Analysis is not available yet. No message has been sent.',
      ),
      findsOneWidget,
    );
  });
}