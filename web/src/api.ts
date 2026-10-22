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
  title: 'Title',
  category: 'Category',
  place_name: 'Place',
  latitude: 'Map pin',
  longitude: 'Map pin',
  original_language: 'Language',
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
  options: { method?: string; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const hasBody = options.body !== undefined
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, {
      method: options.method ?? (hasBody || options.form ? 'POST' : 'GET'),
      headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
      // A FormData body sets its own multipart content type.
      body: options.form ?? (hasBody ? JSON.stringify(options.body) : undefined),
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
