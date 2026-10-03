/**
 * miningSignature 的測試（node 內建 assert）。資料是 scunpacked-data 的真實名稱。
 *
 *   cd frontend && npm run test:mining
 */
import assert from 'node:assert/strict'
import { mineralBaseName, ownSignatures } from './miningSignature.js'

let n = 0
const t = (name, fn) => { fn(); n++ }
const sigs = (name, deps) => ownSignatures(name, deps).map(s => s.signature)

t('完全同名', () => {
  assert.deepEqual(sigs('Hephaestanite (R)', [
    { deposit_name: 'Hephaestanite (R)', signature: 4180, tier: 'common' },
    { deposit_name: 'Granite Deposit', signature: 4000 },
  ]), [4180])
})

t('礦物有 (Ore) 後綴、礦床沒有：Stileron', () => {
  assert.deepEqual(sigs('Stileron (Ore)', [
    { deposit_name: 'Asteroid (C-Type)', signature: 4700 },
    { deposit_name: 'Stileron', signature: 3185, tier: 'legendary' },
    { deposit_name: 'Stileron', signature: 3185, tier: 'legendary' },
  ]), [3185])
})

t('礦物有 Raw 前綴：Ouratite', () => {
  assert.deepEqual(sigs('Raw Ouratite', [
    { deposit_name: 'Ouratite', signature: 3370 },
    { deposit_name: 'Shale Deposit', signature: 4000 },
  ]), [3370])
})

t('有完全同名的就不退回去後綴比對：Carinite (Pure) 不吃到 Carinite 的值', () => {
  assert.deepEqual(sigs('Carinite (Pure)', [
    { deposit_name: 'Carinite (Pure)', signature: 3000 },
    { deposit_name: 'Carinite', signature: 3000 },
    { deposit_name: 'Carinite', signature: 4000 },
  ]), [3000])
})

t('同名礦床有兩種值都列、依值去重排序', () => {
  assert.deepEqual(sigs('Janalite', [
    { deposit_name: 'Janalite', signature: 4000 },
    { deposit_name: 'Janalite', signature: 3000 },
    { deposit_name: 'Janalite', signature: 3000 },
  ]), [3000, 4000])
})

t('RS 為 0 的（FPS）排除；沒有同名礦床回空', () => {
  assert.deepEqual(sigs('Aphorite', [{ deposit_name: 'Aphorite', signature: 0 }]), [])
  assert.deepEqual(sigs('Copper', [{ deposit_name: 'Shale Deposit', signature: 4000 }]), [])
  assert.deepEqual(sigs('', []), [])
})

t('mineralBaseName', () => {
  assert.equal(mineralBaseName('Stileron (Ore)'), 'stileron')
  assert.equal(mineralBaseName('Raw Ice'), 'ice')
  assert.equal(mineralBaseName('Hephaestanite (R)'), 'hephaestanite')
  assert.equal(mineralBaseName('Carinite (Pure)'), 'carinite')
})

console.log(`miningSignature: ${n} passed`)
