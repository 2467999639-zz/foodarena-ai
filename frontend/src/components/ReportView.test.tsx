import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportView } from '../components/ReportView';
import type { DebateReport } from '../types';

const report: DebateReport = {
  dish: '川味小面',
  cuisine: 'sichuan',
  reason: '预算内、暖胃且对味',
  confidence: 0.92,
  score_breakdown: { taste: 4.8, budget: 5.0, weather: 4.5, debate: 4.2 },
};

describe('ReportView', () => {
  it('renders dish, reason, confidence and the four dimensions', () => {
    render(<ReportView report={report} onStartAgain={() => {}} />);

    expect(screen.getByText('川味小面')).toBeInTheDocument();
    expect(screen.getByText(/推荐置信度 92%/)).toBeInTheDocument();
    expect(screen.getByText('预算内、暖胃且对味')).toBeInTheDocument();
    for (const label of ['口味', '预算', '天气', '辩论表现']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('floors a score that is out of range without crashing', () => {
    render(
      <ReportView
        report={{
          ...report,
          score_breakdown: { taste: 0, budget: 0, weather: 0, debate: 0 },
        }}
        onStartAgain={() => {}}
      />,
    );
    expect(screen.getByText('川味小面')).toBeInTheDocument();
  });
});
