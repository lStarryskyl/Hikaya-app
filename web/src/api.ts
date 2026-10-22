export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type ValidationItem = { loc?: (string | number)[]; msg?: string }

const FIELD_NAMES: Record<string, string> = {
  email: 'Email',
  password: 'Password',
  display_name: 'Name',
}

// FastAPI sends `detail` as a string for our own errors and as a list for validation errors.
function describe(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as ValidationItem
    const field = FIELD_NAMES[String(first.loc?.[first.loc.length - 1] ?? '')]
    return field ? `${field} is not valid.` : 'Please check what you entered.'
  }
  return status >= 500 ? 'Something went wrong on our side. Please try again.' : 'Request failed.'
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const hasBody = options.body !== undefined
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, {
      method: options.method ?? (hasBody ? 'POST' : 'GET'),
      headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
      body: hasBody ? JSON.stringify(options.body) : undefined,
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is it running?')
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, describe(data, res.status))
  return data as T
}
