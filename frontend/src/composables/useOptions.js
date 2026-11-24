// Career goals, skills and academic levels from the database (GET /api/options), loaded once per page load.
import { ref } from 'vue'
import { accountApi } from '@/api'

const options = ref({ careerGoals: [], skills: [], academicLevels: [] })
let pending = null

export function useOptions() {
  if (!pending) {
    pending = accountApi.getOptions()
      .then((o) => { options.value = o; return o })
      .catch((e) => { pending = null; throw e })
  }
  return { options, ready: pending }
}
