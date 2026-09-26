import { describe, expect, it } from 'vitest';
import { formatArea, formatLength } from '../src/units';
describe('units', () => {
  it('formats feet and inches', () => {
    expect(formatLength(1.2192)).toBe("4' 0\"");
    expect(formatLength(0.4572)).toBe('18 in');
    expect(formatLength(3.4)).toBe("11' 2\"");
    expect(formatLength(1.0, 'metric')).toBe('1.00 m');
    expect(formatLength(0.45, 'metric')).toBe('45 cm');
    expect(formatArea(10.2)).toBe('110 sq ft');
  });
});
