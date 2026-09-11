import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PreferenceForm } from '../components/PreferenceForm';

function renderForm() {
  const onSubmit = vi.fn();
  render(<PreferenceForm onSubmit={onSubmit} submitting={false} />);
  return { onSubmit };
}

describe('PreferenceForm', () => {
  it('shows field-level errors for invalid input', () => {
    renderForm();

    fireEvent.click(screen.getByText('开始辩论 🔥'));

    expect(screen.getByText('请填写想吃的口味，如「麻辣」「清淡」')).toBeInTheDocument();
  });

  it('validates budget out of range', () => {
    renderForm();
    fireEvent.change(screen.getByPlaceholderText('例如：麻辣 / 清淡 / 酸甜'), {
      target: { value: '麻辣' },
    });
    const budgetInput = screen.getAllByRole('spinbutton')[0];
    fireEvent.change(budgetInput, { target: { value: '999' } });

    fireEvent.click(screen.getByText('开始辩论 🔥'));

    expect(screen.getByText('预算需在 1–200 元之间')).toBeInTheDocument();
  });

  it('submits valid preferences', () => {
    const { onSubmit } = renderForm();

    fireEvent.change(screen.getByPlaceholderText('例如：麻辣 / 清淡 / 酸甜'), {
      target: { value: '清淡' },
    });
    fireEvent.click(screen.getByText('晴')); // weather chip default is 晴
    fireEvent.click(screen.getByText('开始辩论 🔥'));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const submit = onSubmit.mock.calls[0][0];
    expect(submit.preferences.taste).toBe('清淡');
    expect(submit.preferences.budget_yuan).toBe(15);
    expect(submit.preferences.companions).toBe(1);
    // Custom persona/settings stay off unless the user opts in.
    expect(submit.personas).toBeUndefined();
    expect(submit.settings).toBeUndefined();
  });

  it('includes custom personas and settings when enabled', () => {
    const { onSubmit } = renderForm();

    fireEvent.change(screen.getByPlaceholderText('例如：麻辣 / 清淡 / 酸甜'), {
      target: { value: '麻辣' },
    });
    fireEvent.click(screen.getByText('自定义大厨性格与辩论规则'));

    const submit = () => fireEvent.click(screen.getByText('开始辩论 🔥'));
    submit();

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const call = onSubmit.mock.calls[0][0];
    expect(call.personas).toHaveLength(2);
    expect(call.personas[0].agent).toBe('sichuan_spicy');
    expect(call.settings?.early_stop).toBe(true);
    expect(call.settings?.min_rounds).toBe(2);
  });
});
